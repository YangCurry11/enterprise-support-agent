"""签收事实回归：全部使用固定数据或Mock，不调用供应商。"""
from copy import deepcopy
import json
import socket
from types import SimpleNamespace
import uuid
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from support_agent import llm_client, business_db
from support_agent.app import app
from support_agent.model_runtime import CallLedger, ModelServiceError, model_calls
from support_agent.order_facts import build_order_facts, receipt_summary
from support_agent.reply_safety import reply_violations


ORDER = {"order_id": "ORD1001", "status": "已发货", "received_days": None,
         "logistics_company": "顺丰", "tracking_number": "SF123456789"}
POLICIES = [{"source": "refund_policy.md", "text": "非质量问题商品支持签收后7天内申请无理由退货，商品需保持完好。"}]


def test_shipped_null_receipt_does_not_allow_unsigned_claim():
    text = "订单 ORD1001 当前状态为已发货。您的订单目前尚未签收。依据 refund_policy.md，退款需核实具体条件。"
    assert "unsupported_receipt_state" in reply_violations(text, ORDER, POLICIES)


@pytest.fixture(autouse=True)
def forbid_model_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("real_network_forbidden")))


@pytest.mark.parametrize("status,days,expected", [
    ("已发货", None, "unknown"), ("待发货", None, "unknown"),
    ("已签收", None, "received"), ("已签收", 0, "received"), ("已签收", 10, "received"),
    ("售后处理中", 12, "received"), ("已发货", 0, "received"),
    ("未签收", None, "not_received"), ("未收货", None, "not_received"),
    ("未签收", 0, "unknown"), ("未签收", 3, "unknown"),
    ("已发货", -1, "unknown"), ("已发货", False, "unknown"), ("已发货", True, "unknown"),
    ("已发货", "0", "unknown"), ("已发货", 0.5, "unknown"),
])
def test_receipt_state_comes_from_explicit_evidence(status, days, expected):
    raw = {**ORDER, "status": status, "received_days": days}
    before = deepcopy(raw)
    facts = build_order_facts(raw)
    assert facts.receipt.state == expected
    assert raw == before
    assert facts.refund_eligibility == "not_determined"
    assert facts.receipt.conflicting_evidence == (status == "未签收" and type(days) is int and days >= 0)


def test_unknown_facts_ignore_forecasts_or_injected_receipt_objects():
    raw = {**ORDER, "estimated_delivery": "已于昨天签收", "receipt": {"state": "not_received"},
           "facts": {"receipt": {"state": "received", "received_days": 0}}}
    facts = build_order_facts(raw)
    assert facts.receipt.state == "unknown" and facts.receipt.received_days is None
    assert facts.receipt.evidence == []
    assert {"receipt.state", "receipt.received_days", "refund_eligibility"}.issubset(facts.unknown_fields)


def test_missing_logistics_are_unknown_not_negative_receipt():
    facts = build_order_facts({**ORDER, "logistics_company": "", "tracking_number": None, "estimated_delivery": " "})
    assert facts.receipt.state == "unknown"
    assert all(value is None for value in facts.logistics.values())
    assert "logistics.tracking_number" in facts.unknown_fields
    assert build_order_facts(None).receipt.state == "unknown"


@pytest.mark.parametrize("claim", ["您的订单目前尚未签收", "您的包裹还未收货", "您已经签收", "您已收到商品"])
def test_receipt_assertions_are_checked_against_unknown_facts_not_one_phrase(claim):
    reply = f"订单 ORD1001 当前已发货。{claim}。依据 refund_policy.md，需要核实退款条件。"
    assert "unsupported_receipt_state" in reply_violations(reply, ORDER, POLICIES)


@pytest.mark.parametrize("text", [
    "如果您尚未签收，请核实物流；如果已签收，请提供日期。",
    "若您已经签收，是否符合签收后7天内等政策条件仍需核实。",
    "目前无法确认是否已签收及签收时间，请提供实际签收情况。",
    "需核实是否还未收货。",
    "请问您已经签收了吗？",
    "您已签收了吗？",
])
def test_conditional_policy_and_explicit_uncertainty_are_not_order_assertions(text):
    reply = "订单 ORD1001 当前已发货。" + text + "依据 refund_policy.md。"
    assert reply_violations(reply, ORDER, POLICIES) == []


def test_one_conditional_clause_does_not_hide_later_unsupported_assertion():
    reply = "订单 ORD1001 已发货。如果已经签收，需要核实日期，但您的订单尚未签收。依据 refund_policy.md。"
    assert "unsupported_receipt_state" in reply_violations(reply, ORDER, POLICIES)


@pytest.mark.parametrize("status,days,claim,expected", [
    ("已签收", 0, "已签收0天", []),
    ("已签收", None, "已签收，签收天数未知", []),
    ("已签收", None, "已签收3天", ["unsupported_received_days"]),
    ("已签收", 10, "已签收3天", ["unsupported_received_days"]),
    ("未签收", None, "您的订单尚未签收", []),
    ("未签收", None, "您已收货", ["unsupported_receipt_state"]),
])
def test_known_receipt_and_elapsed_days_constraints(status, days, claim, expected):
    raw = {**ORDER, "status": status, "received_days": days}
    reply = f"订单 ORD1001 当前状态{status}。{claim}。依据 refund_policy.md，具体政策适用仍需核实。"
    assert reply_violations(reply, raw, POLICIES) == expected


@pytest.mark.parametrize("status,days", [("已发货",None),("已签收",None),("已签收",0),("未签收",None),("未签收",3)])
def test_deterministic_receipt_summary_uses_the_same_facts(status, days):
    facts = build_order_facts({**ORDER, "status": status, "received_days": days})
    summary = receipt_summary(facts)
    if facts.receipt.state == "unknown":
        assert "无法确认是否签收" in summary
    if facts.receipt.state == "received" and days == 0:
        assert "已签收0天" in summary
    if facts.receipt.state == "received" and days is None:
        assert "签收天数未知" in summary


def test_scoped_and_compatibility_order_tools_add_facts_without_changing_raw_data():
    from support_agent.scoped_tools import ScopedTools
    from support_agent.tools import SupportTools
    business_db.seed_business_db_from_json()
    tool = ScopedTools("U1001", "receipt-test")
    result = tool.query_order("ORD1001")
    assert result["data"] == business_db.get_order("ORD1001") and result["data"]["received_days"] is None
    assert result["facts"]["receipt"]["state"] == "unknown"
    assert "facts" not in result["data"]
    denied = tool.query_order("ORD1002")
    assert not denied["ok"] and "data" not in denied and "facts" not in denied
    legacy = SupportTools(api_client=SimpleNamespace(query_order=lambda _id: deepcopy(ORDER)), kb=object())
    assert legacy.query_order("ORD1001")["facts"] == build_order_facts(ORDER).model_dump()


@pytest.mark.parametrize("status,days", [("已发货",None),("已签收",None),("已签收",0),("未签收",None),("未签收",3)])
def test_policy_template_does_not_turn_unknown_or_conflicting_records_into_facts(status, days):
    from support_agent.agents import AgentState, ResponseAgent
    raw = {**ORDER, "status":status, "received_days":days}
    state = AgentState("那它可以退款吗", intent="refund_policy", order_id="ORD1001", retrieved_docs=POLICIES,
                       tool_results={"query_order":{"ok":True,"data":raw}})
    result = ResponseAgent().run(state)
    assert receipt_summary(build_order_facts(raw)) in result.final_response
    assert reply_violations(result.final_response, raw, POLICIES) == []


@pytest.fixture
def model_stub(monkeypatch):
    for name, value in {"LLM_API_KEY":"offline-receipt-placeholder", "LLM_BASE_URL":"https://offline.invalid/v1",
                        "LLM_MODEL":"offline-receipt-model", "LLM_TIMEOUT_SECONDS":"0.1", "LLM_MAX_RETRIES":"2",
                        "LLM_TEMPERATURE":"0.2", "LLM_INTENT_ENABLED":"false"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    captured = []
    def install(reply):
        def invoke(prompt):
            captured.append(prompt.to_messages())
            content = reply(prompt) if callable(reply) else reply
            return AIMessage(content=content, usage_metadata={"input_tokens":1,"output_tokens":1,"total_tokens":2})
        monkeypatch.setattr(llm_client, "get_llm", lambda: RunnableLambda(invoke))
    return install, captured


def test_prompt_separates_unknown_receipt_from_history_and_policy_conditions(model_stub):
    install, captured = model_stub
    reply = "订单 ORD1001 已发货，目前无法确认是否已签收及签收时间。依据 refund_policy.md，如果签收后7天内且商品完好，可申请退货，仍需核实。"
    install(reply)
    result = llm_client.generate_customer_reply("那它可以退款吗", "refund_policy", order_info=ORDER, policy_docs=POLICIES,
        conversation_context={"receipt":{"state":"not_received"}, "history":[{"role":"assistant","content":"您已经签收"}]})
    assert result == reply
    system, human = captured[0]
    normalized = json.loads(human.content.split("结构化业务事实",1)[1].split("：\n",1)[1].split("\n\n政策依据",1)[0])
    assert normalized["receipt"]["state"] == "unknown" and normalized["receipt"]["received_days"] is None
    assert normalized["refund_eligibility"] == "not_determined"
    assert "received_days=null" in system.content and "已发货不等于未签收" in system.content


def test_bad_model_claim_fails_closed_without_retries(model_stub):
    install, captured = model_stub
    install("订单 ORD1001 已发货。您的订单目前尚未签收。依据 refund_policy.md，退款条件需核实。")
    ledger = CallLedger(5, simulated=True)
    with model_calls(ledger), pytest.raises(ModelServiceError) as error:
        llm_client.generate_customer_reply("它可以退款吗", "refund_policy", order_info=ORDER, policy_docs=POLICIES)
    assert error.value.code == "unsafe_reply" and len(captured) == len(ledger.calls) == 1
    trace = llm_client.last_model_trace()
    assert not trace["model_used"] and trace["fallback_used"]
    assert "unsupported_receipt_state" in trace["fact_violations"]


@pytest.mark.parametrize("raw,state,reply", [
    ({**ORDER,"status":"已签收"}, "received", "订单 ORD1001 当前已签收，但签收天数未知。依据 refund_policy.md，需核实具体日期及其他条件。"),
    ({**ORDER,"status":"未签收"}, "not_received", "订单 ORD1001 当前未签收。依据 refund_policy.md，具体政策适用仍需核实。"),
    ({**ORDER,"tracking_number":"","logistics_company":""}, "unknown", "订单 ORD1001 当前已发货，物流信息缺失，目前无法确认是否签收。依据 refund_policy.md，需要补充实际签收情况。"),
])
def test_model_prompt_and_validation_accept_known_or_explicitly_unknown_facts(model_stub, raw, state, reply):
    install, captured = model_stub
    install(reply)
    assert llm_client.generate_customer_reply("那它可以退款吗", "refund_policy", order_info=raw, policy_docs=POLICIES) == reply
    human = captured[0][-1].content
    normalized = json.loads(human.split("结构化业务事实",1)[1].split("：\n",1)[1].split("\n\n政策依据",1)[0])
    assert normalized["receipt"]["state"] == state
    assert llm_client.last_model_trace()["model_used"]


def test_model_receipt_error_falls_back_and_preserves_graph_review_and_idempotency(model_stub, isolated_environment):
    from support_agent.runtime import WorkflowService
    install, _ = model_stub
    def reply(prompt):
        if "识别出的意图：\nrefund_policy" in prompt.to_messages()[-1].content:
            return "订单 ORD1001 已发货。您的订单目前尚未签收。依据 refund_policy.md，退款条件需核实。"
        return "订单 ORD1001 已发货，顺丰单号 SF123456789。"
    install(reply)
    ledger = CallLedger(8, simulated=True)
    headers = {"Authorization":"Bearer customer-1"}
    with model_calls(ledger), TestClient(app) as client:
        cid = client.post("/agent/conversations", json={}, headers=headers).json()["conversation_id"]
        def message(text, key=None):
            response = client.post(f"/agent/conversations/{cid}/messages", headers=headers,
                                   json={"content":text,"request_id":key or str(uuid.uuid4())})
            assert response.status_code == 200
            return response.json()
        first = message("我的订单 ORD1001 到哪了？")
        second = message("那它可以退款吗？")
        assert first["status"] == second["status"] == "completed"
        assert second["tool_results"]["query_order"]["facts"]["receipt"]["state"] == "unknown"
        assert "无法确认是否签收" in second["final_response"] and "您的订单目前尚未签收" not in second["final_response"]
        detail = second["steps"][-1]["detail"]
        assert detail["mode"] == "fallback_template" and detail["error"] == "unsafe_reply"
        assert "unsupported_receipt_state" in detail["model_trace"]["fact_violations"]
        key = str(uuid.uuid4())
        third = message("那帮我申请售后吧。", key)
        assert len({first["run_id"],second["run_id"],third["run_id"]}) == 3
        assert third["order_id"] == "ORD1001" and third["status"] == "awaiting_review"
        assert business_db.list_tickets() == []
        endpoint = f"/agent/runs/{third['run_id']}/review"
        assert client.post(endpoint, headers=headers, json={"approved":True}).status_code == 403
        app.state.workflows = WorkflowService(isolated_environment)
        completed = client.post(endpoint, headers={"Authorization":"Bearer reviewer"}, json={"approved":True}).json()
        repeated = client.post(endpoint, headers={"Authorization":"Bearer reviewer"}, json={"approved":True}).json()
        resent = message("那帮我申请售后吧。", key)
        assert completed["status"] == "completed"
        assert third["run_id"] == completed["run_id"] == repeated["run_id"] == resent["run_id"]
        assert len(business_db.list_tickets()) == 1 and len(ledger.calls) == 2


def test_receipt_regression_uses_existing_evaluator_and_ignores_stale_facts():
    from evaluation.evaluators.reply_eval import facts
    from evaluation.evaluators import receipt_eval
    from evaluation.run_evaluation import load
    result = {"status":"completed", "final_response":"订单 ORD1001 已发货。您尚未签收。依据 refund_policy.md。",
              "retrieved_docs":POLICIES,
              "tool_results":{"query_order":{"ok":True,"data":ORDER,"facts":{"receipt":{"state":"not_received"}}}}}
    checks, violations = facts(result)
    assert not checks["receipt_facts_consistent"] and "unsupported_receipt_state" in violations
    report = receipt_eval.evaluate(load("receipt_cases.jsonl"))
    assert report["metrics"]["passed"] == report["metrics"]["sample_count"] == 14, report
    assert report["metrics"]["actual_model_calls"] == 0
    assert all("pending" in row["annotation_source"] for row in load("receipt_cases.jsonl"))


def test_offline_cli_includes_receipt_regression_without_model_calls(tmp_path, monkeypatch):
    from evaluation.run_evaluation import main
    monkeypatch.setenv("LLM_API_KEY", "offline-must-ignore")
    assert main(["--mode","offline","--output",str(tmp_path)]) == 0
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert report["receipt"]["metrics"]["passed"] == 14 and report["model_calls"]["actual_model_calls"] == 0
    assert "receipt" in (tmp_path/"summary.md").read_text(encoding="utf-8")
