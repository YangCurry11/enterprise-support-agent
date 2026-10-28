"""Citation contract and native SDK protocol; every HTTP completion is mocked."""
from contextlib import contextmanager
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_openai import ChatOpenAI

from support_agent import app as api, business_db, llm_client, tool_calling as tc
from support_agent.agents import AgentState
from support_agent.model_runtime import CallLedger, model_calls
from support_agent.scoped_tools import ScopedTools

BASE = "订单ORD1001当前状态为已发货，目前无法确认是否签收及签收时间。"


@pytest.mark.parametrize("sources", [["refund_policy.md"], ["shipping_policy.md", "membership_policy.md"], []])
def test_contract_citation_spec_follows_actual_sources(sources):
    state = AgentState("政策问题", intent="refund_policy",
                       retrieved_docs=[{"source": s, "text": "模拟政策片段", "chunk_id": str(i)} for i, s in enumerate(sources)])
    contract = tc.reply_contract(state)
    assert contract["policy_sources"] == sorted(sources)
    assert contract["policy_citation"] == {
        "required": bool(sources), "format": "【来源：<source>】",
        "examples": [f"【来源：{s}】" for s in sorted(sources)]}


@contextmanager
def policy_sdk(monkeypatch, answer, *, sequential=False):
    for key, value in {"LLM_TOOL_CALLING_ENABLED": "true", "LLM_TOOL_MAX_ROUNDS": "2",
                       "LLM_TOOL_MAX_CALLS": "3", "LLM_TOOL_MAX_MODEL_CALLS": "4",
                       "LLM_MODEL": "qwen-offline-citations", "LLM_API_KEY": "offline-not-secret",
                       "LLM_BASE_URL": "https://offline.invalid/v1", "LLM_MAX_RETRIES": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    def blocked(*_a, **_k):
        raise AssertionError("Unexpected external network")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    requests, policies, candidates = [], [], []
    def call(name, args, identifier):
        return {"id": identifier, "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert {t["function"]["name"] for t in body["tools"]} == {"query_order", "search_policy"}
        assert "【来源：<source>】" in body["messages"][0]["content"]
        question = json.loads(body["messages"][1]["content"])["question"]
        messages = [m for m in body["messages"] if m["role"] == "tool"]
        if not messages:
            planned = [call("query_order", {"order_id": "ORD1001"}, "citation-order")]
            if not sequential:
                planned.append(call("search_policy", {"query": question, "top_k": 3}, "citation-policy"))
            message = {"role": "assistant", "content": None, "tool_calls": planned}
        elif sequential and not any(m.get("tool_call_id") == "citation-policy" for m in messages):
            message = {"role": "assistant", "content": None, "tool_calls": [
                call("search_policy", {"query": question, "top_k": 3}, "citation-policy")]}
        else:
            # OpenAI ToolMessage wire envelopes identify the tool by call ID;
            # LangChain need not serialize the optional name field.
            tool = next(m for m in messages if m.get("tool_call_id") == "citation-policy")
            assert tool["tool_call_id"] == "citation-policy"
            payload = json.loads(tool["content"])
            policies.append(payload)
            sources = sorted({d["source"] for d in payload["data"]})
            assert payload["reply_contract"]["policy_sources"] == sources
            assert payload["reply_contract"]["policy_citation"]["examples"] == [f"【来源：{s}】" for s in sources]
            text = answer(payload) if callable(answer) else answer
            candidates.append(text)
            message = {"role": "assistant", "content": text}
        return httpx.Response(200, json={"id": "mock-policy", "object": "chat.completion", "created": 1,
            "model": "qwen-offline-citations", "choices": [{"index": 0, "message": message,
                "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        model = ChatOpenAI(model="qwen-offline-citations", api_key="offline-not-secret",
                           base_url="https://offline.invalid/v1", max_retries=0, http_client=http)
        monkeypatch.setattr(llm_client, "get_llm", lambda: model)
        yield requests, policies, candidates


def ask(client):
    headers = {"Authorization": "Bearer customer-1"}
    cid = client.post("/agent/conversations", headers=headers, json={}).json()["conversation_id"]
    response = client.post(f"/agent/conversations/{cid}/messages", headers=headers,
                           json={"content": "订单ORD1001的退款政策是什么？", "request_id": str(uuid.uuid4())})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("suffix,errors", [
    ("【来源：refund_policy.md】", []),
    ("依据refund_policy.md。", []),
    ("依据\u0060refund_policy.md\u0060。", []),
    ("依据[退款政策](refund_policy.md)。", []),
    ("依据《退款政策》。", ["missing_source"]),
    ("", ["missing_source"]),
    ("【来源：invented_policy.md】", ["unsupported_source", "missing_source"]),
    ("【来源：shipping_policy.md】", ["unsupported_source", "missing_source"]),
    ("【来源：refund_policy.md】【来源：invented_policy.md】", ["unsupported_source"]),
    ("【来源：REFUND_POLICY.md】", ["unsupported_source", "missing_source"]),
    ("【来源：refund_policy.md】您的订单已经签收。", ["unsupported_receipt_state"]),
    ("【来源：refund_policy.md】您的订单尚未签收。", ["unsupported_receipt_state"]),
])
def test_native_policy_citation_and_fact_boundaries(monkeypatch, suffix, errors):
    candidate = BASE + suffix
    ledger = CallLedger(8, simulated=True)
    with policy_sdk(monkeypatch, candidate) as (requests, policies, _), TestClient(api.app) as client, model_calls(ledger):
        result = ask(client)
    trace = result["tool_calling_trace"]
    assert len(requests) == len(ledger.calls) == 2
    assert {d["source"] for d in policies[0]["data"]} == {"refund_policy.md"}
    assert policies[0]["data"] == result["tool_results"]["search_policy"]["data"]
    assert policies[0]["reply_contract"]["receipt"]["state"] == "unknown"
    assert trace["reply_validation"]["violations"] == errors
    assert trace["reply_validation"]["policy_source_present"] is ("refund_policy.md" in candidate)
    if errors:
        assert trace["status"] == "fallback" and trace["error_type"] == "unsafe_reply"
        assert result["final_response"] != candidate and ledger.calls[-1]["error_type"] == "unsafe_reply"
    else:
        assert trace["status"] == "model_generated" and result["final_response"] == candidate
    assert business_db.list_tickets() == []


def test_empty_policy_evidence_cannot_generate_a_policy_conclusion(monkeypatch):
    monkeypatch.setattr(ScopedTools, "search_policy", lambda *_a, **_k: {"ok": True, "data": []})
    candidate = BASE + "依据refund_policy.md，本订单满足退款条件。"
    with policy_sdk(monkeypatch, candidate) as (_, policies, _), TestClient(api.app) as client:
        result = ask(client)
    trace = result["tool_calling_trace"]
    assert not policies[0]["data"] and not policies[0]["reply_contract"]["policy_citation"]["required"]
    assert policies[0]["reply_contract"]["policy_citation"]["examples"] == []
    assert trace["status"] == "fallback" and trace["error_type"] == "missing_required_evidence"
    assert result["final_response"] != candidate and result["retrieved_docs"] == []
    assert "refund_policy.md" not in result["final_response"]


def test_sequential_native_tools_use_evidence_derived_citation_without_appending(monkeypatch):
    def answer(payload):
        return BASE + payload["reply_contract"]["policy_citation"]["examples"][0]
    with policy_sdk(monkeypatch, answer, sequential=True) as (requests, policies, candidates), TestClient(api.app) as client:
        result = ask(client)
    assert len(requests) == 3 and result["tool_calling_trace"]["status"] == "model_generated"
    assert result["final_response"] == candidates[0]  # No server-side fixed citation suffix.
    assert policies[0]["reply_contract"]["policy_sources"] == ["refund_policy.md"]
