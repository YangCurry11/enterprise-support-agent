"""Phase 3A: deterministic offline vectors/SDK MockTransport, no paid requests."""
from dataclasses import replace
import hashlib
import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
import numpy as np
import pytest
from openai import OpenAI
from support_agent.config import POLICY_DIR
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import RagSettings, EmbeddingSettings
from support_agent.embedding_client import EmbeddingClient, EmbeddingError, EmbeddingLedger, normalized_vectors, minimize_query
from support_agent.rag_index import DenseIndex, manifest, build_index, query_key
from support_agent.dense_retriever import DenseRetriever
from support_agent.hybrid_retriever import HybridRetriever


@pytest.fixture(autouse=True)
def no_remote(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("remote forbidden")))
    for key, value in {"RAG_MODE":"tfidf", "EMBEDDING_ENABLED":"false", "RAG_REMOTE_QUERY_ENABLED":"false",
                       "EMBEDDING_MODEL":"test-embedding", "EMBEDDING_BASE_URL":"https://test.invalid/v1",
                       "EMBEDDING_DIMENSIONS":"2", "EMBEDDING_API_KEY":"offline-test-not-secret",
                       "EMBEDDING_MAX_RETRIES":"0"}.items():
        monkeypatch.setenv(key, value)


def settings():
    return EmbeddingSettings.read()


def response(vectors, usage=True):
    return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=v) for i, v in enumerate(vectors)],
                           usage=SimpleNamespace(prompt_tokens=11, total_tokens=11) if usage else None)


def client_stub(result=None, error=None, cfg=None):
    sdk = SimpleNamespace(embeddings=SimpleNamespace(create=Mock(return_value=result, side_effect=error)))
    return EmbeddingClient(cfg or settings(), sdk), sdk.embeddings.create


def tiny_kb(tmp_path):
    (tmp_path/"a.md").write_text("# 标题\n\n## 退款\n退回规则\n\n## 物流\n快递规则", encoding="utf-8")
    return PolicyKnowledgeBase(tmp_path, settings=RagSettings())


def test_default_tfidf_and_original_contract():
    kb = PolicyKnowledgeBase()
    hits = kb.search("超过7天还能退款吗", 3)
    assert hits and hits[0]["source"] == "refund_policy.md"
    assert all({"source", "text", "score"}.issubset(h) for h in hits)
    assert all(h["score_type"] == "tfidf_cosine" for h in hits)
    assert kb.settings.mode == "tfidf" and kb._dense is None
    assert kb.search_with_trace("退货")["retrieval"]["embedding_calls"]["actual_embedding_calls"] == 0


def test_chunk_ids_headings_and_original_split_are_stable(tmp_path):
    kb = tiny_kb(tmp_path)
    other = PolicyKnowledgeBase(tmp_path, settings=RagSettings())
    assert [c.chunk_id for c in kb.chunks] == [c.chunk_id for c in other.chunks]
    assert len({c.chunk_id for c in kb.chunks}) == len(kb.chunks)
    assert [c.text for c in kb.chunks] == kb._split_markdown((tmp_path/"a.md").read_text(encoding="utf-8"))
    assert kb.chunks[1].heading == "退款"
    for c in kb.chunks:
        assert c.content_hash == hashlib.sha256(c.text.encode()).hexdigest()
        assert c.source == "a.md"


def test_cache_roundtrip_and_query_cache_no_network(tmp_path):
    kb = tiny_kb(tmp_path)
    vectors = [[1, 0]] * len(kb.chunks)
    index = DenseIndex(kb.chunks, settings(), vectors, query_vectors={query_key("退款"): [1, 0]})
    path = tmp_path/"index.json"
    index.save(path)
    loaded = DenseIndex.load(path, kb.chunks, settings())
    assert np.allclose(loaded.vectors, index.vectors)
    dense = DenseRetriever(loaded, kb.chunks)
    assert dense.search("退款", 2, EmbeddingLedger(1))
    assert loaded.metadata == manifest(kb.chunks, settings())


@pytest.mark.parametrize("change", ["model", "dimensions", "base_url", "split", "corpus", "mock", "corrupt"])
def test_cache_mismatch_and_mock_are_never_used_as_real(tmp_path, change):
    kb = tiny_kb(tmp_path)
    path = tmp_path/"index.json"
    index = DenseIndex(kb.chunks, settings(), [[1, 0]] * len(kb.chunks))
    index.save(path)
    expected = settings()
    if change in {"model", "dimensions", "base_url"}:
        expected = replace(expected, **{change: {"model":"other", "dimensions":3, "base_url":"https://other.invalid/v1"}[change]})
    elif change == "split":
        raw=json.loads(path.read_text()); raw["metadata"]["split_version"]="v999"; path.write_text(json.dumps(raw))
    elif change == "corpus":
        (tmp_path/"a.md").write_text("# changed", encoding="utf-8"); kb=PolicyKnowledgeBase(tmp_path, settings=RagSettings())
    elif change == "mock":
        index.provenance="mock"; index.save(path)
    else:
        path.write_text("broken json")
    with pytest.raises(EmbeddingError):
        DenseIndex.load(path, kb.chunks, expected)


def test_atomic_failure_preserves_prior_cache(tmp_path, monkeypatch):
    from support_agent import rag_index
    kb=tiny_kb(tmp_path); index=DenseIndex(kb.chunks, settings(), [[1, 0]]*len(kb.chunks)); path=tmp_path/"index.json"
    index.save(path); before=path.read_bytes()
    monkeypatch.setattr(rag_index.os, "replace", Mock(side_effect=OSError("simulated disk failure")))
    with pytest.raises(OSError): index.save(path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_dense_cosine_and_ties_deterministic(tmp_path):
    kb=tiny_kb(tmp_path)
    index=DenseIndex(kb.chunks, settings(), [[1,0], [0,1], [1,1]], query_vectors={query_key("q"):[1,0]})
    dense=DenseRetriever(index,kb.chunks)
    hits=dense.search("q",3,EmbeddingLedger(1))
    assert [h["chunk_id"] for h in hits] == [kb.chunks[i].chunk_id for i in (0,2,1)]
    tied=DenseIndex(kb.chunks, settings(), [[1,0]]*3, query_vectors={query_key("q"):[1,0]})
    ranked=DenseRetriever(tied,kb.chunks).search("q",3,EmbeddingLedger(1))
    assert [h["chunk_id"] for h in ranked] == sorted(c.chunk_id for c in kb.chunks)
    assert ranked == DenseRetriever(tied,kb.chunks).search("q",3,EmbeddingLedger(1))


def test_rrf_uses_ranks_not_scores_and_deduplicates():
    sparse=[{"chunk_id":"a", "source":"a.md", "text":"a", "score":.001}, {"chunk_id":"b", "score":100}]
    dense=[{"chunk_id":"b", "score":-.8}, {"chunk_id":"a", "score":.9}]
    hits=HybridRetriever(60).search(sparse,dense,3)
    assert [h["chunk_id"] for h in hits] == ["a","b"]
    assert hits[0]["score"] == pytest.approx(1/61+1/62)
    assert hits[0]["score_type"] == "rrf" and hits[0]["tfidf_rank"] == 1 and hits[0]["dense_rank"] == 2
    assert len(HybridRetriever().search([sparse[0],sparse[0]], [sparse[0]],5)) == 1


@pytest.mark.parametrize("values,dim,code", [([[0,0]],2,"invalid_vector"), ([[float("nan"),1]],2,"invalid_vector"),
    ([[float("inf"),1]],2,"invalid_vector"), ([[1]],2,"dimension_mismatch"), ([["1","2"]],2,"dimension_mismatch"),
    ([[True,False]],2,"dimension_mismatch")])
def test_bad_vectors(values,dim,code):
    with pytest.raises(EmbeddingError, match=code): normalized_vectors(values,1,dim)


@pytest.mark.parametrize("error,expected", [(TimeoutError("secret must not leak"),"timeout"),
    (type("Unauthorized",(Exception,),{"status_code":401})("secret"),"authentication_error"),
    (type("Forbidden",(Exception,),{"status_code":403})("secret"),"authentication_error"),
    (type("RateLimited",(Exception,),{"status_code":429})("secret"),"rate_limit"),
    (type("Provider",(Exception,),{"status_code":503})("secret"),"provider_error")])
def test_error_classification_and_no_secret_body(error,expected):
    client,create=client_stub(error=error)
    ledger=EmbeddingLedger(1)
    with pytest.raises(EmbeddingError,match=expected) as raised: client.embed(["policy"],ledger)
    assert "secret" not in str(raised.value) and "secret" not in json.dumps(ledger.summary())
    assert len(ledger.calls) == create.call_count == 1


def test_retries_cannot_exceed_embedding_budget_or_change_chat_ledger():
    from support_agent.model_runtime import CallLedger, model_calls
    client,create=client_stub(error=TimeoutError(),cfg=replace(settings(),max_retries=2))
    ledger=EmbeddingLedger(2); chat=CallLedger(5)
    with model_calls(chat),pytest.raises(EmbeddingError,match="budget_exhausted"): client.embed(["policy"],ledger)
    assert create.call_count == 2 and len(ledger.calls) == 2 and not chat.calls


def test_retry_then_success_usage_and_invalid_vectors_not_retried():
    client,create=client_stub(cfg=replace(settings(),max_retries=2))
    create.side_effect=[TimeoutError(),response([[3,4]])]
    ledger=EmbeddingLedger(3)
    assert np.allclose(client.embed(["x"],ledger),[[.6,.8]])
    assert ledger.summary()["token_usage"] == {"input_tokens":11,"total_tokens":11}
    assert not ledger.summary()["usage_complete"] and ledger.summary()["cost"] is None
    client,create=client_stub(response([[0,0]]),cfg=replace(settings(),max_retries=2))
    with pytest.raises(EmbeddingError):client.embed(["x"],EmbeddingLedger(3))
    assert create.call_count == 1


def test_sdk_payload_ordering_usage_and_hidden_retries():
    observed=[]
    def transport(request):
        observed.append(json.loads(request.content))
        return httpx.Response(200,json={"object":"list","model":"test-embedding", "data":[
            {"object":"embedding","index":1,"embedding":[0,1]}, {"object":"embedding","index":0,"embedding":[1,0]}],
            "usage":{"prompt_tokens":9,"total_tokens":9}})
    sdk=OpenAI(api_key="offline-not-a-secret",base_url="https://test.invalid/v1",max_retries=0,
               http_client=httpx.Client(transport=httpx.MockTransport(transport)))
    ledger=EmbeddingLedger(1)
    matrix=EmbeddingClient(settings(),sdk).embed(["one","two"],ledger)
    assert matrix.tolist() == [[1,0],[0,1]]
    assert observed == [{"input":["one","two"],"model":"test-embedding","dimensions":2,"encoding_format":"float"}]
    assert ledger.summary()["token_usage"] == {"input_tokens":9,"total_tokens":9}
    assert ledger.summary()["usage_complete"]


def test_missing_usage_is_null():
    client,_=client_stub(response([[1,0]],False)); ledger=EmbeddingLedger(1)
    client.embed(["x"],ledger)
    assert ledger.summary()["token_usage"] is None


@pytest.mark.parametrize("reason", ["timeout","authentication_error","rate_limit","dimension_mismatch","index_missing",
    "index_stale","invalid_vector","similarity_error","budget_exhausted"])
@pytest.mark.parametrize("mode", ["dense","hybrid"])
def test_all_vector_failures_fall_back_without_losing_policy_sources(mode,reason):
    kb=PolicyKnowledgeBase(settings=RagSettings(mode=mode,enabled=True),embedding_settings=settings(),
                           dense=SimpleNamespace(search=Mock(side_effect=EmbeddingError(reason))))
    result=kb.search_with_trace("退款")
    assert result["data"] and result["retrieval"]["configured_mode"] == mode
    assert result["retrieval"]["actual_mode"] == "tfidf" and result["retrieval"]["fallback_reason"] == reason
    assert result["retrieval"]["embedding_model"] == "test-embedding"
    assert all(h["score_type"] == "tfidf_cosine" for h in result["data"])


def test_missing_index_never_calls_remote_or_rebuilds(tmp_path):
    kb=PolicyKnowledgeBase(settings=RagSettings(mode="hybrid",enabled=True,remote_query=True,cache_dir=tmp_path),embedding_settings=settings())
    assert kb.search_with_trace("退款")["retrieval"]["fallback_reason"] == "index_missing"
    assert not list(tmp_path.iterdir())


def test_remote_query_is_disabled_even_with_real_cache_and_key(tmp_path):
    kb=PolicyKnowledgeBase(settings=RagSettings(mode="dense",enabled=True,cache_dir=tmp_path),embedding_settings=settings())
    DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks)).save(tmp_path/"policy_index.json")
    result=kb.search_with_trace("退款")
    assert result["retrieval"]["fallback_reason"] == "query_not_cached_remote_disabled"
    assert result["retrieval"]["embedding_calls"]["actual_embedding_calls"] == 0


def test_query_redaction_before_remote_and_memory_reuse(tmp_path):
    kb=tiny_kb(tmp_path); client,create=client_stub(response([[1,0]]))
    index=DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks))
    retriever=DenseRetriever(index,kb.chunks,client,remote_query=True); ledger=EmbeddingLedger(1)
    query="订单ORD1001给我打13812345678 邮箱a@b.com 还有SF123456789"
    retriever.search(query,3,ledger); retriever.search(query,3,ledger)
    assert create.call_count == 1
    sent=create.call_args.kwargs["input"][0]
    assert all(v not in sent for v in ("ORD1001","13812345678","a@b.com","SF123456789"))
    assert sent == minimize_query(query)


def test_changed_policy_is_not_served_from_old_dense_cache(tmp_path):
    kb=tiny_kb(tmp_path); kb.settings=RagSettings(mode="dense",enabled=True,cache_dir=tmp_path)
    kb.embedding_settings=settings()
    DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks)).save(tmp_path/"policy_index.json")
    (tmp_path/"a.md").write_text("# 新政策\n\n退款新规则",encoding="utf-8")
    result=kb.search_with_trace("退款")
    assert result["retrieval"]["fallback_reason"] == "index_stale"
    assert "新规则" in result["data"][0]["text"]


@pytest.mark.parametrize("key,value",[("RAG_MODE","evil"),("RAG_RRF_K","0"),("RAG_CANDIDATES","NaN"),
    ("EMBEDDING_ENABLED","yes"),("RAG_QUERY_MAX_EMBEDDING_CALLS","0"),("RAG_REMOTE_QUERY_ENABLED","1")])
def test_bad_server_rag_configuration(key,value,monkeypatch):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):RagSettings.read()


@pytest.mark.parametrize("key,value",[("EMBEDDING_MODEL",""),("EMBEDDING_BASE_URL","http://remote.invalid/v1"),
    ("EMBEDDING_BASE_URL","https://user:password@test.invalid/v1"),("EMBEDDING_DIMENSIONS","0"),
    ("EMBEDDING_TIMEOUT_SECONDS","NaN"),("EMBEDDING_MAX_RETRIES","3")])
def test_embedding_config_never_uses_chat_defaults(key,value,monkeypatch):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):EmbeddingSettings.read()


def test_offline_comparison_preserves_misses_and_negatives(tmp_path):
    from evaluation.compare_rag import main
    output=tmp_path/"comparison"
    assert main(["--mode","offline","--output",str(output)]) == 0
    report=json.loads((output/"latest.json").read_text(encoding="utf-8"))
    assert report["embedding_source"] == "mock_dense" and report["embedding_calls"]["actual_embedding_calls"] == 0
    assert report["embedding_calls"]["token_usage"] is None and report["embedding_calls"]["cost"] is None
    for mode in ("tfidf","dense","hybrid"):
        result=report["datasets_results"]["hard16"][mode]
        assert len(result["cases"]) == 16 and result["metrics"]["negative_count"] == 3
        assert result["failures"] and all(r["review_status"] == "pending" for r in result["cases"])
    assert report["datasets_results"]["historical20"]["tfidf"]["metrics"]["recall_at_1"] == .95
    assert report["datasets_results"]["historical20"]["tfidf"]["metrics"]["mrr"] == .9625
    with pytest.raises(SystemExit):main(["--output",str(output)])


def test_offline_builder_writes_mock_not_production_index(tmp_path):
    from evaluation.build_policy_index import main
    output=tmp_path/"build"
    assert main(["--output",str(output),"--include-eval-queries"]) == 0
    report=json.loads((output/"latest.json").read_text())
    assert report["source"] == "mock_dense" and report["embedding_calls"]["actual_embedding_calls"] == 0
    assert json.loads((output/"mock_index.json").read_text())["provenance"] == "mock"


@pytest.mark.parametrize("module",["evaluation.build_policy_index","evaluation.compare_rag"])
def test_cli_requires_explicit_remote_permission_and_budget(module,tmp_path):
    import importlib
    with pytest.raises(SystemExit):importlib.import_module(module).main(["--mode","live","--output",str(tmp_path/"out")])
    assert not (tmp_path/"out").exists()


def test_hard_gold_is_verified_not_adapted_to_predictions():
    from evaluation.rag_comparison import validate_cases
    from evaluation.run_evaluation import load
    kb=PolicyKnowledgeBase(); cases=load("rag_hard_cases.jsonl")
    validate_cases(cases,kb)
    with pytest.raises(ValueError):validate_cases([{**cases[0],"gold_evidence":"invented policy"}],kb)


def test_live_builder_reuses_valid_index_without_api(tmp_path,monkeypatch):
    from evaluation.build_policy_index import main
    monkeypatch.setenv("EMBEDDING_ENABLED","true");monkeypatch.setenv("RAG_CACHE_DIR",str(tmp_path/"cache"))
    kb=PolicyKnowledgeBase(settings=RagSettings())
    index=DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks))
    index.save(tmp_path/"cache/policy_index.json")
    assert main(["--mode","live","--allow-remote","--max-embedding-calls","1","--output",str(tmp_path/"run")]) == 0
    report=json.loads((tmp_path/"run/latest.json").read_text())
    assert report["status"] == "reused" and report["embedding_calls"]["actual_embedding_calls"] == 0


def test_hybrid_integrates_original_graph_review_and_single_ticket(monkeypatch):
    from evaluation.mock_embedding import MockEmbedding
    from evaluation.sandbox import sandbox, REVIEWER
    from support_agent import business_db
    kb=PolicyKnowledgeBase(settings=RagSettings())
    cfg=EmbeddingSettings("MOCK-test", "https://mock.invalid/v1",128)
    client=MockEmbedding(); index=build_index(kb.chunks,cfg,client,EmbeddingLedger(1)); index.provenance="mock"
    hybrid=PolicyKnowledgeBase(settings=RagSettings(mode="hybrid",enabled=True),embedding_settings=cfg,
        dense=DenseRetriever(index,kb.chunks,client,remote_query=True))
    with sandbox() as box, patch("support_agent.scoped_tools.policy_index", return_value=hybrid):
        cid=box.conversation(); first=box.message(cid,"我的订单 ORD1001 到哪了？")
        second=box.message(cid,"那它可以退款吗？")
        assert first["order_id"] == second["order_id"] == "ORD1001"
        assert second["tool_results"]["search_policy"]["retrieval"]["actual_mode"] == "hybrid"
        assert all(h["score_type"] == "rrf" for h in second["retrieved_docs"])
        assert "无法确认是否签收" in second["final_response"]
        third=box.message(cid,"那帮我申请售后吧。", "6b728a0e-2805-4f68-b6c8-728a989e15ba")
        assert third["status"] == "awaiting_review" and business_db.list_tickets() == []
        endpoint=f"/agent/runs/{third['run_id']}/review"
        assert box.call("POST",endpoint,{"approved":True}).status_code == 403
        approved=box.json("POST",endpoint,{"approved":True},REVIEWER)
        repeated=box.json("POST",endpoint,{"approved":True},REVIEWER)
        assert third["run_id"] == approved["run_id"] == repeated["run_id"]
        assert len(business_db.list_tickets()) == 1 and "不代表退款" in approved["final_response"]


def test_original_offline_cli_ignores_live_embedding_environment(tmp_path,monkeypatch):
    from evaluation.run_evaluation import main
    monkeypatch.setenv("RAG_MODE","hybrid");monkeypatch.setenv("EMBEDDING_ENABLED","true")
    monkeypatch.setenv("RAG_REMOTE_QUERY_ENABLED","true")
    monkeypatch.setattr(EmbeddingClient,"embed",Mock(side_effect=AssertionError("must not call")))
    assert main(["--mode","offline","--output",str(tmp_path)]) == 0
    assert not EmbeddingClient.embed.called


def test_real_cached_comparison_without_key_or_remote(tmp_path,monkeypatch):
    from evaluation.run_evaluation import load
    from evaluation.compare_rag import main
    kb=PolicyKnowledgeBase(settings=RagSettings())
    queries=[c["query"] for name in ("rag_cases.jsonl","rag_hard_cases.jsonl") for c in load(name)]
    # Synthetic stand-in for a real-produced cache, ONLY in this isolated test.
    index=DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks),query_vectors={query_key(q):[1,0] for q in queries})
    index.save(tmp_path/"cache/policy_index.json")
    monkeypatch.setenv("RAG_CACHE_DIR",str(tmp_path/"cache"));monkeypatch.setenv("EMBEDDING_API_KEY","")
    monkeypatch.setattr(EmbeddingClient,"embed",Mock(side_effect=AssertionError("must not call")))
    assert main(["--source","cache","--output",str(tmp_path/"compare")]) == 0
    report=json.loads((tmp_path/"compare/latest.json").read_text(encoding="utf-8"))
    assert report["embedding_source"] == "real_cached_dense"
    assert report["embedding_calls"]["actual_embedding_calls"] == 0
    assert not EmbeddingClient.embed.called


def test_live_builder_failure_records_budget_without_overwriting_index(tmp_path,monkeypatch):
    from evaluation.build_policy_index import main
    monkeypatch.setenv("EMBEDDING_ENABLED","true");monkeypatch.setenv("RAG_CACHE_DIR",str(tmp_path/"cache"))
    monkeypatch.setattr(EmbeddingClient,"embed",Mock(side_effect=EmbeddingError("budget_exhausted")))
    output=tmp_path/"failed"
    assert main(["--mode","live","--allow-remote","--max-embedding-calls","1","--output",str(output)]) == 1
    report=json.loads((output/"latest.json").read_text())
    assert report["status"] == "failed" and report["error_type"] == "budget_exhausted"
    assert not (tmp_path/"cache/policy_index.json").exists()


def test_sdk_retry_disabled_at_actual_http_transport():
    calls=[]
    def transport(request):
        calls.append(request)
        return httpx.Response(429,json={"error":{"message":"redacted","type":"rate_limit"}})
    sdk=OpenAI(api_key="offline-test",base_url="https://test.invalid/v1",max_retries=0,
               http_client=httpx.Client(transport=httpx.MockTransport(transport)))
    cfg=replace(settings(),max_retries=2); ledger=EmbeddingLedger(2)
    with pytest.raises(EmbeddingError,match="budget_exhausted"):EmbeddingClient(cfg,sdk).embed(["x"],ledger)
    assert len(calls) == len(ledger.calls) == 2


def test_auth_failure_never_retries_even_when_configured():
    error=type("Unauthorized",(Exception,),{"status_code":401})("do not leak")
    client,create=client_stub(error=error,cfg=replace(settings(),max_retries=2))
    with pytest.raises(EmbeddingError,match="authentication_error"):client.embed(["x"],EmbeddingLedger(3))
    assert create.call_count == 1


def test_known_v4_dimension_configuration_and_repr(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL","text-embedding-v4");monkeypatch.setenv("EMBEDDING_DIMENSIONS","17")
    with pytest.raises(ValueError):EmbeddingSettings.read()
    monkeypatch.setenv("EMBEDDING_DIMENSIONS","1024")
    cfg=EmbeddingSettings.read()
    assert cfg.dimensions == 1024 and "offline-test-not-secret" not in repr(cfg)
    assert "api_key" not in cfg.public()


@pytest.mark.parametrize("fail", [False, True])
def test_owned_sdk_is_closed_after_success_or_error(monkeypatch, fail):
    cfg=replace(settings(), api_key="offline-placeholder", max_retries=0)
    sdk=Mock()
    sdk.__enter__ = Mock(return_value=sdk)
    sdk.__exit__ = Mock(return_value=False)
    sdk.embeddings.create.side_effect=TimeoutError() if fail else None
    sdk.embeddings.create.return_value=response([[1,0]])
    factory=Mock(return_value=sdk)
    monkeypatch.setattr("openai.OpenAI", factory)
    client=EmbeddingClient(cfg)
    if fail:
        with pytest.raises(EmbeddingError, match="timeout"):client.embed(["policy"],EmbeddingLedger(1))
    else:
        assert client.embed(["policy"],EmbeddingLedger(1)).tolist() == [[1,0]]
    sdk.__exit__.assert_called_once()
    assert factory.call_args.kwargs["max_retries"] == 0
    assert client.client is None


def test_injected_sdk_remains_owned_by_caller():
    client,create=client_stub(response([[1,0]]))
    client.client.close=Mock()
    client.embed(["policy"],EmbeddingLedger(1))
    client.client.close.assert_not_called()


@pytest.mark.parametrize("queries", [[], [1], "bad", {"not-a-hash":[1,0]}, {"a"*64:[float("nan"),0]}])
def test_malformed_query_cache_falls_back_safely(tmp_path, queries):
    kb=PolicyKnowledgeBase(settings=RagSettings(mode="hybrid",enabled=True,cache_dir=tmp_path),embedding_settings=settings())
    path=tmp_path/"policy_index.json"
    DenseIndex(kb.chunks,settings(),[[1,0]]*len(kb.chunks)).save(path)
    raw=json.loads(path.read_text());raw["query_vectors"]=queries
    path.write_text(json.dumps(raw))
    with pytest.raises(EmbeddingError):DenseIndex.load(path,kb.chunks,settings())
    result=kb.search_with_trace("退款")
    assert result["retrieval"]["actual_mode"] == "tfidf"
    assert result["retrieval"]["fallback_reason"] in {"index_invalid","invalid_vector"}
    assert result["data"]
