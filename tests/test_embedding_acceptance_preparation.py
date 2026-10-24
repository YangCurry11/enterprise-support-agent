"""Acceptance preparation is strictly offline, including with live flags configured."""
from copy import deepcopy
import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import OpenAI
import pytest

from evaluation import prepare_embedding_acceptance as prep
from support_agent.embedding_client import EmbeddingClient, EmbeddingLedger
from support_agent.rag_config import EmbeddingSettings


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*_a, **_kw):
        raise AssertionError("acceptance preparation may not access the network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.mark.parametrize("url,region", [
    ("https://sample.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "cn-beijing"),
    ("https://sample.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/", "ap-southeast-1"),
    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "cn-beijing"),
    ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "ap-southeast-1"),
    ("https://dashscope.aliyuncs.com.attacker.invalid/compatible-mode/v1", None),
    ("https://sample.cn-beijing.maas.aliyuncs.com.attacker.invalid/compatible-mode/v1", None),
    ("http://dashscope.aliyuncs.com/compatible-mode/v1", None),
    ("https://secret@dashscope.aliyuncs.com/compatible-mode/v1", None),
    ("https://dashscope.aliyuncs.com:444/compatible-mode/v1", None),
    ("https://dashscope.aliyuncs.com/compatible-mode/v1?key=secret", None),
    ("https://dashscope.aliyuncs.com/api/v1", None),
    ("https://<workspace>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", None),
    ("https://[invalid", None),
])
def test_region_recognition_is_strict_and_local(url, region):
    assert prep.endpoint_region(url) == region


def test_configuration_exports_only_presence_not_key_or_workspace(monkeypatch):
    secret = "offline-fixture-not-a-real-key"
    for key, value in {"EMBEDDING_API_KEY": secret, "EMBEDDING_MODEL": "text-embedding-v4",
                       "EMBEDDING_BASE_URL": "https://private-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                       "EMBEDDING_DIMENSIONS": "1024", "EMBEDDING_MAX_RETRIES": "0"}.items():
        monkeypatch.setenv(key, value)
    result = prep.configuration_check()
    assert result["api_key_configured"] is True
    assert result["candidate_model_matches"] is True
    assert result["endpoint_region"] == "cn-beijing"
    assert result["key_region_match"] == "requires_console_confirmation"
    assert secret not in json.dumps(result) and "private-workspace" not in json.dumps(result)
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    assert prep.configuration_check()["api_key_configured"] is False
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "secret-invalid-value")
    result = prep.configuration_check()
    assert result["embedding_configuration_valid"] is False
    assert "secret-invalid-value" not in json.dumps(result)


def test_inventory_preserves_existing_datasets_and_has_no_client(tmp_path, monkeypatch, capsys):
    before = {p: p.read_bytes() for p in (prep.BASE_DIR / "evaluation" / "datasets").glob("rag*.jsonl")}
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("RAG_REMOTE_QUERY_ENABLED", "true")
    monkeypatch.setenv("RAG_MODE", "hybrid")
    monkeypatch.setattr(EmbeddingClient, "embed", Mock(side_effect=AssertionError("no API")))
    monkeypatch.setattr("openai.OpenAI", Mock(side_effect=AssertionError("no SDK construction")))
    output = tmp_path / "plan"
    assert prep.main(["--output", str(output)]) == 0
    result = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    inv = result["inventory"]
    assert result["preparation_embedding_api_calls"] == 0
    assert result["ready_to_call"] is False and result["actual_calls_authorized"] is False
    assert inv["dataset_counts"] == {"rag_cases.jsonl": {"total": 20, "positive": 20, "no_support": 0},
                                      "rag_hard_cases.jsonl": {"total": 16, "positive": 13, "no_support": 3}}
    assert inv["chunks"]["text_count"] == 19
    assert inv["minimized_unique_queries"]["text_count"] == 36
    assert inv["request_plan"]["cold_build_no_retries"] == 6
    assert inv["request_plan"]["potential_attempts_if_budget_expanded"] == {"0": 6, "1": 12, "2": 18}
    assert inv["request_plan"]["warm_complete_cache"] == 0
    assert inv["ndcg_at_3"] is None
    assert all(row["per_mode_evidence_review"]["hybrid"]["supports_question"] is None
               for row in inv["no_support_review_template"])
    assert {p: p.read_bytes() for p in before} == before
    assert "ready_to_call" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        prep.main(["--output", str(output)])
    with pytest.raises(SystemExit):
        prep.main(["--mode", "live"])


def recorded_reports():
    inv = prep.inventory()
    cfg = {"model": "text-embedding-v4", "dimensions": 1024, "endpoint_host": "dashscope.aliyuncs.com"}
    build = {"mode": "live", "source": "live_dense", "status": "built", "configuration": cfg,
             "index_metadata": {"corpus_hash": inv["corpus_hash"]},
             "embedding_calls": {"actual_embedding_calls": 2, "calls": [
                 {"usage": {"input_tokens": 100, "total_tokens": 100}}, {"usage": None}]}}
    comparison = {"embedding_source": "real_cached_dense", "configuration": cfg,
                  "policy_hashes": inv["policy_hashes"], "datasets": inv["dataset_hashes"],
                  "embedding_calls": {"actual_embedding_calls": 0, "calls": []},
                  "datasets_results": {"example": {"dense": {"metrics": {"recall_at_1": .5}, "cases": [
                      {"retrieval": {"actual_mode": "dense", "embedding_attempts_this_search": 0,
                                     "fallback_reason": None, "embedding_calls": {"actual_embedding_calls": 999}}},
                      {"retrieval": {"actual_mode": "tfidf", "embedding_attempts_this_search": 0,
                                     "fallback_reason": "index_missing"}}]}}}}
    return build, comparison


def test_cost_cache_hit_and_unknown_usage_not_zero_or_double_counted():
    build, comparison = recorded_reports()
    result = prep.summarize_recorded(build, comparison, "cn-beijing")
    assert result["recorded_embedding_attempts"] == 2  # Not the per-search cumulative 999.
    assert result["reported_input_tokens"] == 100
    assert result["estimated_cost_from_reported_usage_cny"] == .00005
    assert result["usage_complete"] is False and result["unreported_attempt_usage_count"] == 1
    assert result["cost_is_final_bill"] is False
    assert result["modes"]["example/dense"]["query_cache_hit_rate"] == .5  # Fallback is not a hit.
    assert result["modes"]["example/dense"]["support_evidence_verdict"].startswith("pending")
    for call in build["embedding_calls"]["calls"]:
        call["usage"] = None
    assert prep.summarize_recorded(build, comparison, "cn-beijing")["estimated_cost_from_reported_usage_cny"] is None


@pytest.mark.parametrize("change", ["mock_build", "mock_comparison", "corpus", "dataset", "region", "model", "dimensions", "count"])
def test_postprocessor_rejects_unverified_or_mismatched_artifacts(change):
    build, comparison = deepcopy(recorded_reports())
    if change == "mock_build": build["mode"] = "offline"
    if change == "mock_comparison": comparison["embedding_source"] = "mock_dense"
    if change == "corpus": build["index_metadata"]["corpus_hash"] = "different"
    if change == "dataset": comparison["datasets"]["rag_cases.jsonl"] = "different"
    if change == "region": build["configuration"] = {**build["configuration"], "endpoint_host": "dashscope-intl.aliyuncs.com"}
    if change == "model": build["configuration"] = {**build["configuration"], "model": "chat-model"}
    if change == "dimensions": build["configuration"] = {**build["configuration"], "dimensions": 512}
    if change == "count": build["embedding_calls"]["actual_embedding_calls"] = 3
    with pytest.raises(ValueError): prep.summarize_recorded(build, comparison, "cn-beijing")


def test_minimization_and_findings_do_not_serialize_sensitive_matches():
    inv = prep.inventory()
    assert inv["data_export_review"]["owner_authorization"] == "pending"
    assert inv["data_export_review"]["pattern_scan_is_complete_pii_detection"] is False
    assert inv["token_and_cost_planning"]["actual_tokens"] is None
    assert inv["token_and_cost_planning"]["runtime_token_hard_cap_implemented"] is False


@pytest.mark.parametrize("model,total,prompt,expected", [
    ("text-embedding-v4", 9, None, {"input_tokens": 9, "total_tokens": 9}),
    ("text-embedding-v4", 0, None, {"input_tokens": 0, "total_tokens": 0}),
    ("text-embedding-v4", 9, 9, {"input_tokens": 9, "total_tokens": 9}),
    ("unknown-embedding", 9, None, None),
    ("text-embedding-v4", None, None, None), ("text-embedding-v4", True, None, None),
    ("text-embedding-v4", -1, None, None), ("text-embedding-v4", "9", None, None),
    ("text-embedding-v4", 9, "9", None), ("text-embedding-v4", 8, 9, None),
])
def test_usage_compatibility_remains_provider_based(model, total, prompt, expected):
    usage = SimpleNamespace(total_tokens=total)
    if prompt is not None: usage.prompt_tokens = prompt
    result = SimpleNamespace(usage=usage, data=[SimpleNamespace(index=0, embedding=[1, 0])])
    sdk = SimpleNamespace(embeddings=SimpleNamespace(create=Mock(return_value=result)))
    cfg = EmbeddingSettings(model, "https://test.invalid/v1", 2, max_retries=0)
    ledger = EmbeddingLedger(1)
    EmbeddingClient(cfg, sdk).embed(["synthetic"], ledger)
    assert ledger.summary()["token_usage"] == expected


def test_real_sdk_parses_v4_usage_without_prompt_tokens_using_mock_transport():
    cfg = EmbeddingSettings("text-embedding-v4", "https://test.invalid/v1", 64, max_retries=0)
    def transport(request):
        assert json.loads(request.content)["encoding_format"] == "float"
        return httpx.Response(200, json={"object": "list", "model": cfg.model,
            "data": [{"object": "embedding", "index": 0, "embedding": [1.] + [0.] * 63}],
            "usage": {"total_tokens": 7}})
    with OpenAI(api_key="offline-test-not-secret", base_url=cfg.base_url, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as sdk:
        ledger = EmbeddingLedger(1)
        assert EmbeddingClient(cfg, sdk).embed(["synthetic"], ledger).shape == (1, 64)
    assert ledger.summary()["usage_complete"] is True
    assert ledger.summary()["token_usage"] == {"input_tokens": 7, "total_tokens": 7}
