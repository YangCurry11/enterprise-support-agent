"""Real SDK envelopes via MockTransport only; diagnostics contain no raw reply."""
from contextlib import contextmanager
import json
import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from support_agent import app as api, business_db, llm_client, tool_calling as tc
from support_agent import reply_diagnostics as diagnostic
from support_agent.model_runtime import CallLedger, ModelServiceError, model_calls
from support_agent.order_facts import build_order_facts

GOOD = "订单ORD1001当前状态为已发货，顺丰物流单号SF***6789，预计2天内送达。目前无法确认是否签收及签收时间。"


@pytest.fixture
def tool_mode(monkeypatch):
    for key, value in {"LLM_TOOL_CALLING_ENABLED": "true", "LLM_TOOL_MAX_ROUNDS": "2", "LLM_TOOL_MAX_CALLS": "3",
                       "LLM_TOOL_MAX_MODEL_CALLS": "4", "LLM_MODEL": "qwen-offline-test", "LLM_API_KEY": "offline-not-a-real-key",
                       "LLM_BASE_URL": "https://offline.invalid/v1", "LLM_MAX_RETRIES": "0", "LLM_INTENT_ENABLED": "false"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    def blocked(*_a, **_k):
        raise AssertionError("Unexpected external HTTP transport")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)


@contextmanager
def sdk(monkeypatch, reply):
    requests, payloads = [], []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert {t["function"]["name"] for t in body["tools"]} == {"query_order", "search_policy"}
        assert body["enable_thinking"] is False and body["parallel_tool_calls"] is False
        assert "逐字保留" in body["messages"][0]["content"]
        if len(requests) == 1:
            question = json.loads(body["messages"][1]["content"])
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "sdk-order-1", "type": "function",
                       "function": {"name": "query_order", "arguments": json.dumps({"order_id": question["current_order_id"]})}}]}
        else:
            tool = next(m for m in body["messages"] if m["role"] == "tool")
            assert tool["tool_call_id"] == "sdk-order-1"
            payload = json.loads(tool["content"])
            payloads.append(payload)
            assert payload["facts"] == build_order_facts(payload["data"]).model_dump()
            assert payload["reply_contract"]["receipt"] == payload["facts"]["receipt"]
            assert "user_id" not in payload["data"] and "amount" not in payload["data"]
            message = {"role": "assistant", "content": reply(payload) if callable(reply) else reply}
        return httpx.Response(200, json={"id": "sdk-offline", "object": "chat.completion", "created": 1,
            "model": "qwen-offline-test", "choices": [{"index": 0, "message": message,
                "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        model = ChatOpenAI(model="qwen-offline-test", api_key="offline-not-secret", base_url="https://offline.invalid/v1",
                           max_retries=0, http_client=http)
        monkeypatch.setattr(llm_client, "get_llm", lambda: model)
        yield requests, payloads


def query(client, text="我的订单ORD1001到哪了？"):
    headers = {"Authorization": "Bearer customer-1"}
    cid = client.post("/agent/conversations", headers=headers, json={}).json()["conversation_id"]
    response = client.post(f"/agent/conversations/{cid}/messages", headers=headers,
                           json={"content": text, "request_id": str(uuid.uuid4())})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("reply,error", [
    (GOOD, None),
    ("订单ORD1001已发货，物流单号SF***6789，当前物流状态为已发货。", None),
    ("订单ORD1001已发货，SF***6789。如果已签收，请补充日期；目前无法确认是否签收。", None),
    ("订单ORD1001已发货，SF***6789。如果支付成功，请提供凭证；目前无法确认审批已通过。", None),
    ("订单ORD1001已发货，SF***6789。支付成功后才可核实到账，不能认定审批已通过。", None),
    ("订单ORD1001已发货，SF***6789。没有支付成功的凭证，不能确认退款审批已通过。", None),
    ("订单ORD1001已发货，SF***6789。您的订单已经签收。", "unsupported_receipt_state"),
    ("订单ORD1001已发货，SF***6789。您的订单尚未签收。", "unsupported_receipt_state"),
    ("订单ORD1001已发货，SF***6789。已为您退款。", "unsupported_financial_action"),
    ("订单ORD1001已发货，SF***6789。支付已成功。", "unsupported_payment_action"),
    ("订单ORD1001已发货，SF***6789。退款审批已通过。", "unsupported_approval_action"),
    ("已发货，SF***6789。", "missing_order_id"),
    ("订单ORD1001，SF***6789。", "missing_status"),
    ("订单ORD1001已发货，预计2天内送达。", "missing_tracking_number"),
])
def test_native_sdk_final_reply_checks_and_fallback(tool_mode, monkeypatch, reply, error):
    ledger = CallLedger(8, simulated=True)
    with sdk(monkeypatch, reply) as (requests, payloads), TestClient(api.app) as client, model_calls(ledger):
        result = query(client)
    trace = result["tool_calling_trace"]
    assert len(requests) == len(ledger.calls) == 2 and trace["tool_execution_count"] == 1
    assert trace["model_calls"]["token_usage"]["total_tokens"] == 16  # Mock usage, not provider billing.
    assert result["conversation_context"]["history"] == [] and result["order_id"] == "ORD1001"
    assert payloads[0]["data"] == result["tool_results"]["query_order"]["data"]
    assert payloads[0]["reply_contract"]["required_exact_order_fields"] == {
        "order_id": "ORD1001", "status": "已发货", "tracking_number": "SF***6789"}
    if error:
        assert trace["status"] == "fallback" and trace["error_type"] == "unsafe_reply"
        assert error in trace["reply_validation"]["violations"]
        assert result["final_response"] != reply and trace["fallback_tool_execution_count"] == 0
        assert ledger.calls[-1]["error_type"] == "unsafe_reply" and not ledger.calls[-1]["success"]
    else:
        assert trace["status"] == "model_generated" and result["final_response"] == reply
        assert trace["reply_validation"]["violations"] == []
    assert business_db.list_tickets() == []


@pytest.mark.parametrize("status,days,reply,expected", [
    ("已签收", 0, "订单ORD1001已签收，SF***6789，工具记录已签收0天。", "received"),
    ("已签收", None, "订单ORD1001已签收，SF***6789，签收天数未知。", "received"),
    ("未签收", None, "订单ORD1001未签收，SF***6789，工具明确记录尚未签收。", "not_received"),
])
def test_explicit_receipt_states_still_pass_native_protocol(tool_mode, monkeypatch, status, days, reply, expected):
    with sdk(monkeypatch, reply) as (_, payloads), TestClient(api.app) as client:
        with business_db.get_connection() as connection:
            connection.execute("UPDATE orders SET status=?,received_days=? WHERE order_id='ORD1001'", (status, days))
        result = query(client)
    assert result["tool_calling_trace"]["status"] == "model_generated"
    assert payloads[0]["facts"]["receipt"]["state"] == expected


def test_missing_logistics_remains_unknown(tool_mode, monkeypatch):
    reply = "订单ORD1001已发货，物流信息缺失，无法确认是否签收。"
    with sdk(monkeypatch, reply) as (_, payloads), TestClient(api.app) as client:
        with business_db.get_connection() as connection:
            connection.execute("UPDATE orders SET tracking_number='',logistics_company='',estimated_delivery='' WHERE order_id='ORD1001'")
        result = query(client)
    assert result["tool_calling_trace"]["status"] == "model_generated"
    assert payloads[0]["facts"]["receipt"]["state"] == "unknown"
    assert "tracking_number" not in payloads[0]["reply_contract"]["required_exact_order_fields"]


def test_protocol_mismatch_is_blocked_before_next_sdk_request(tool_mode, monkeypatch):
    class BrokenToolMessage(ToolMessage):
        def __init__(self, **kwargs):
            super().__init__(**{**kwargs, "tool_call_id": "wrong-call-id"})
    monkeypatch.setattr(tc, "ToolMessage", BrokenToolMessage)
    ledger = CallLedger(8, simulated=True)
    with sdk(monkeypatch, GOOD) as (requests, _), TestClient(api.app) as client, model_calls(ledger):
        result = query(client)
    assert len(requests) == len(ledger.calls) == 1
    assert result["tool_calling_trace"]["error_type"] == "tool_protocol_mismatch"
    assert result["tool_calling_trace"]["status"] == "fallback"


@pytest.mark.parametrize("mode", ["denied", "budget"])
def test_denial_and_budget_never_send_a_second_model_request(tool_mode, monkeypatch, mode):
    if mode == "budget":
        monkeypatch.setenv("LLM_TOOL_MAX_MODEL_CALLS", "1")
    with sdk(monkeypatch, GOOD) as (requests, _), TestClient(api.app) as client:
        result = query(client, "查询ORD1002" if mode == "denied" else "查询ORD1001")
    trace = result["tool_calling_trace"]
    assert len(requests) == 1 and trace["model_calls"]["actual_model_calls"] == 1
    assert trace["error_type"] == ("order_unavailable" if mode == "denied" else "budget_exhausted")
    if mode == "denied":
        assert trace["status"] == "blocked" and not result["tool_results"]["query_order"]["ok"]
        assert "U1002" not in json.dumps(result) and "机械键盘" not in str(result)


@pytest.mark.parametrize("case", ["orphan", "missing", "duplicate", "wrong_name", "valid"])
def test_tool_message_pairing_contract(case):
    messages = [SystemMessage(content="规则"), HumanMessage(content="问题"), AIMessage(content="", tool_calls=[
        {"name": "query_order", "args": {"order_id": "ORD1001"}, "id": "one", "type": "tool_call"}])]
    tool = ToolMessage(content="{}", tool_call_id="one", name="query_order")
    messages = [tool] if case == "orphan" else messages + ([] if case == "missing" else [tool])
    if case == "duplicate": messages.append(tool)
    if case == "wrong_name": messages[-1] = ToolMessage(content="{}", tool_call_id="one", name="search_policy")
    if case == "valid":
        tc.validate_tool_messages(messages)
    else:
        with pytest.raises(ModelServiceError, match="tool_protocol_mismatch"):
            tc.validate_tool_messages(messages)


def test_opt_in_diagnostic_has_no_raw_reply_or_private_values(tool_mode, monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    secret = "sk-" + "synthetic-private-probe" * 2
    candidate = f"订单ORD1001已发货，SF***6789。已经签收。张三13800138000 person@example.test {secret}。"
    with sdk(monkeypatch, candidate), TestClient(api.app) as client:
        result = query(client)
    files = list((tmp_path / ".local_diagnostics/reply_safety").glob("*.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    for private in (candidate, secret, "张三", "13800138000", "person@example.test", "ORD1001", "SF***6789"):
        assert private not in text and private not in caplog.text
    assert candidate not in json.dumps(result, ensure_ascii=False)
    record = json.loads(text)
    assert record["projection_is_lossy"] and "unsupported_receipt_state" in record["violations"]
    assert record["facts_summary"]["receipt_state"] == "unknown"
    public = result["tool_calling_trace"]["reply_validation"]
    assert public["local_diagnostic"]["recorded"] and "candidate_projection" not in public


@pytest.mark.parametrize("flag", ["false", "invalid"])
def test_diagnostics_are_off_by_default_or_bad_setting(monkeypatch, tmp_path, flag):
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", flag)
    result = diagnostic.record_rejection("private-value", ["missing_status"], {}, "run")
    assert not result["recorded"] and not (tmp_path / ".local_diagnostics").exists()


def test_diagnostic_metadata_is_allowlisted_and_capture_failure_is_nonfatal(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    summary = {"receipt_state": "unknown", "private": "private-value", "required_fields_present": {"status": True, "private": "private-value"}}
    assert diagnostic.record_rejection("private-value", ["private-value"], summary, "private-value")["recorded"]
    path = next((tmp_path / ".local_diagnostics/reply_safety").glob("*.json"))
    assert "private-value" not in path.read_text(encoding="utf-8")
    monkeypatch.setattr(diagnostic.os, "open", lambda *_a, **_k: (_ for _ in ()).throw(OSError("private-error")))
    assert not diagnostic.record_rejection("已签收", ["unsupported_receipt_state"], {}, "run")["recorded"]


def test_diagnostic_file_limit_does_not_delete_existing_records(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    folder = tmp_path / ".local_diagnostics/reply_safety"
    folder.mkdir(parents=True)
    for index in range(50): (folder / f"{index}.json").write_text("{}", encoding="utf-8")
    result = diagnostic.record_rejection("已签收", ["unsupported_receipt_state"], {}, "run")
    assert result["status"] == "limit_reached" and len(list(folder.glob("*.json"))) == 50


def test_diagnostic_failure_preserves_unsafe_reply_and_fallback(tool_mode, monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    # os.open is also used by temporary infrastructure: start the isolated app first.
    with sdk(monkeypatch, "订单ORD1001已发货，SF***6789。您的订单尚未签收。"), TestClient(api.app) as client:
        monkeypatch.setattr(diagnostic.os, "open", lambda *_a, **_k: (_ for _ in ()).throw(OSError("capture unavailable")))
        result = query(client)
    trace = result["tool_calling_trace"]
    assert trace["status"] == "fallback" and trace["error_type"] == "unsafe_reply"
    assert not trace["reply_validation"]["local_diagnostic"]["recorded"]
    assert trace["fallback_tool_execution_count"] == 0


@pytest.mark.parametrize("summary", [None, {"receipt_state": [], "required_fields_present": []}])
def test_malformed_diagnostic_metadata_cannot_escape_allowlist(monkeypatch, tmp_path, summary):
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    result = diagnostic.record_rejection("private-value", [{}], summary, "run")
    assert result["recorded"]
    record = json.loads(next((tmp_path / ".local_diagnostics/reply_safety").glob("*.json")).read_text(encoding="utf-8"))
    assert record["facts_summary"]["receipt_state"] == "unknown"
    assert record["violations"] == ["unclassified_violation"]


def test_diagnostic_refuses_linked_capture_folder(monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setattr(diagnostic, "BASE_DIR", tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == ".local_diagnostics" or original(self))
    result = diagnostic.record_rejection("已签收", ["unsupported_receipt_state"], {}, "run")
    assert not result["recorded"] and not (tmp_path / ".local_diagnostics").exists()


def test_diagnostics_preserve_explicit_live_opt_in_but_offline_always_disables(monkeypatch):
    from evaluation.evaluate_tool_calling import tool_environment
    monkeypatch.setenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "true")
    with tool_environment(live=False):
        assert os.getenv("LLM_REPLY_DIAGNOSTICS_ENABLED") == "false"
    with tool_environment(live=True):  # Configuration only, no messages/model invocation.
        assert os.getenv("LLM_REPLY_DIAGNOSTICS_ENABLED") == "true"
