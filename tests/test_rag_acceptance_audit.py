"""Synthetic report fixtures ONLY: never evidence of a real provider invocation."""
from copy import deepcopy
import json
import socket
from unittest.mock import Mock

import pytest

from evaluation import audit_rag_acceptance as audit
from evaluation.compare_rag import main as compare, write_comparison
from evaluation.prepare_embedding_acceptance import inventory, summarize_recorded
from support_agent.embedding_client import EmbeddingClient
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import EmbeddingSettings, RagSettings
from support_agent.rag_index import manifest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("report audit must not invoke a network client")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(EmbeddingClient, "embed", Mock(side_effect=forbidden))


@pytest.fixture
def records(tmp_path):
    # Only relabel local mock data to exercise artifact validation. These fixtures
    # are isolated under tmp_path, not real acceptance reports or model results.
    output = tmp_path / "synthetic-mock"
    assert compare(["--mode", "offline", "--output", str(output)]) == 0
    first = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    cfg = {"model": "text-embedding-v4", "dimensions": 64, "endpoint_host": "dashscope.aliyuncs.com"}
    first.update(embedding_source="real_cached_dense", configuration=cfg)
    for modes in first["datasets_results"].values():
        for mode, result in modes.items():
            label = "tfidf_baseline" if mode == "tfidf" else "real_cached_dense"
            result["source_label"] = label
            for row in result["cases"]:
                row["source_label"] = label
                row["retrieval"]["embedding_model"] = cfg["model"] if mode != "tfidf" else None
    kb = PolicyKnowledgeBase(settings=RagSettings())
    plan = inventory()
    count = plan["request_plan"]["cold_build_no_retries"]
    calls = [{"model": cfg["model"], "success": True, "error_type": None, "attempt": 1,
              "usage": {"input_tokens": 1, "total_tokens": 1}} for _ in range(count)]
    build = {"mode": "live", "source": "live_dense", "status": "built", "configuration": cfg,
             "chunk_count": len(kb.chunks), "query_count_requested": 36,
             "index_metadata": manifest(kb.chunks, EmbeddingSettings(cfg["model"], "https://dashscope.aliyuncs.com/compatible-mode/v1", 64)),
             "embedding_calls": {"actual_embedding_calls": count, "max_embedding_calls": count, "calls": calls,
                                 "usage_complete": True, "usage_reported_calls": count,
                                 "token_usage": {"input_tokens": count, "total_tokens": count}}}
    summary = {"inventory": plan, "recorded_results": summarize_recorded(build, first, "cn-beijing")}
    return build, first, deepcopy(first), summary


def test_audit_and_pending_sheet_are_offline_and_do_not_change_inputs(records, tmp_path):
    before = deepcopy(records)
    result = audit.audit(*records)
    assert result["compared_case_mode_rows"] == 108
    assert result["compared_candidate_rows"] == 540
    assert result["top_k_reproducible"] is True
    assert result["audit_model_api_calls"] == 0
    assert result["automatic_safe_refusal_verified"] is False
    assert result["ndcg_at_3"] is None
    assert records == before
    sheet = audit.evidence_sheet(records[1])
    assert sheet.count("人工总体结论：待填写") == 36
    assert all(case in sheet for case in ("hard-14", "hard-15", "hard-16"))
    assert "完整片段" in sheet and "独立人工支持判定" in sheet
    args = []
    for name, report in zip(("build", "first", "repeat", "summary"), records):
        p = tmp_path / (name + ".json")
        p.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        args += ["--" + name, str(p)]
    output = tmp_path / "audit"
    assert audit.main(args + ["--output", str(output)]) == 0
    assert (output / "evidence_review.md").is_file()
    with pytest.raises(SystemExit):
        audit.main(args + ["--output", str(output)])


@pytest.mark.parametrize("change", ["score", "order", "rank", "content", "gold", "missing_case", "mode", "fallback", "calls", "metric", "manifest", "usage", "summary", "source_hash", "row_label", "dimensions"])
def test_corruption_or_nonreproducibility_blocks_audit(records, change):
    build, first, repeat, summary = deepcopy(records)
    row = repeat["datasets_results"]["historical20"]["dense"]["cases"][0]
    if change == "score": row["hits"][0]["score"] += .01
    if change == "order": row["hits"][0], row["hits"][1] = row["hits"][1], row["hits"][0]
    if change == "rank": row["hits"][0]["dense_rank"] = 9
    if change == "content": row["hits"][0]["text"] = "invented policy"
    if change == "gold": row["gold_evidence"] = "invented gold"
    if change == "missing_case": repeat["datasets_results"]["hard16"]["hybrid"]["cases"].pop()
    if change == "mode": repeat["embedding_source"] = "mock_dense"
    if change == "fallback": row["retrieval"].update(actual_mode="tfidf", fallback_reason="timeout")
    if change == "calls": repeat["embedding_calls"]["actual_embedding_calls"] = 1
    if change == "metric": repeat["datasets_results"]["historical20"]["dense"]["metrics"]["mrr"] = 0
    if change == "manifest": build["index_metadata"]["dimensions"] = 128
    if change == "usage": build["embedding_calls"]["calls"][0]["usage"]["input_tokens"] = -1
    if change == "summary": summary["recorded_results"]["reported_input_tokens"] += 1
    if change == "source_hash": repeat["source_hashes"]["evaluation/compare_rag.py"] = "changed"
    if change == "row_label": row["source_label"] = "mock_dense"
    if change == "dimensions": repeat["configuration"] = {**repeat["configuration"], "dimensions": 128}
    with pytest.raises(ValueError):
        audit.audit(build, first, repeat, summary)


@pytest.mark.parametrize("source,expected,absent", [
    ("mock_dense", "Mock只验证算法与工程", "使用真实Embedding缓存"),
    ("real_cached_dense", "使用真实Embedding缓存", "Mock只验证算法与工程"),
    ("live_dense", "显式在线查询向量化", "Mock只验证算法与工程"),
])
def test_report_description_follows_actual_source(tmp_path, source, expected, absent):
    output = tmp_path / source
    write_comparison({"embedding_source": source, "datasets_results": {}}, output)
    text = (output / "summary.md").read_text(encoding="utf-8")
    assert expected in text and absent not in text
    assert "fallback不得当Dense成功" in text


def test_unknown_report_source_is_not_silently_mislabeled(tmp_path):
    output = tmp_path / "unknown"
    with pytest.raises(ValueError):
        write_comparison({"embedding_source": "unknown", "datasets_results": {}}, output)
    assert not output.exists()


def test_evidence_text_escapes_html_and_markdown():
    escaped = audit.md('<script>evil</script> ![x](https://example.invalid) | *claim*')
    assert '<script>' not in escaped and r'\[' in escaped and r'\|' in escaped
