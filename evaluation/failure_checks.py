"""E 类故障注入始终离线；复用客户端重试/解析与真实工作流，不连供应商。"""
from unittest.mock import patch
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from support_agent.model_runtime import CallLedger, model_calls
from .sandbox import sandbox, REVIEWER


class InjectedServiceError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__("private-provider-body-must-not-leak")


class FaultModel(RunnableLambda):
    def __init__(self, kind):
        self.kind = kind
        def invoke(_input):
            if kind == "timeout":
                raise TimeoutError("private-provider-body-must-not-leak")
            if kind == "invalid_response":
                return AIMessage(content="")
            if kind == "unsafe_reply":
                return AIMessage(content="已为您退款，退款已到账。")
            raise InjectedServiceError({"authentication_error": 401, "rate_limit": 429, "provider_error": 503}[kind])
        super().__init__(invoke)

    def with_structured_output(self, *_args, **_kwargs):
        if self.kind in {"invalid_response", "unsafe_reply"}:
            return RunnableLambda(lambda _: {"raw": AIMessage(content=""), "parsed": None, "parsing_error": ValueError("private-provider-body-must-not-leak")})
        return self


def evaluate():
    from support_agent import llm_client, business_db
    rows = []
    for kind in ("timeout", "invalid_response", "authentication_error", "rate_limit", "provider_error", "unsafe_reply"):
        ledger = CallLedger(20, simulated=True)
        with sandbox(live=True, intent_live=True) as box, model_calls(ledger), patch.dict("os.environ", {
            "LLM_API_KEY": "offline-injected-placeholder", "LLM_BASE_URL": "https://offline.invalid/v1",
            "LLM_MODEL": "offline-injected-model", "LLM_MAX_RETRIES": "1", "LLM_TIMEOUT_SECONDS": "0.1",
            "LLM_TEMPERATURE": "0.2"}), patch.object(llm_client, "get_llm", return_value=FaultModel(kind)):
            cid = box.conversation()
            order = box.message(cid, "我的订单 ORD1001 到哪了？")
            intent_trace = next(s["detail"]["model_trace"] for s in order["steps"] if s["name"] == "IntentAgent")
            reply = order["steps"][-1]["detail"]
            pending = box.message(cid, "我要投诉")
            before = business_db.list_tickets()
            endpoint = f"/agent/runs/{pending['run_id']}/review"
            denied = box.call("POST", endpoint, {"approved": True})
            completed = box.json("POST", endpoint, {"approved": True}, REVIEWER)
            count = len(ledger.calls)
            repeated = box.json("POST", endpoint, {"approved": True}, REVIEWER)
            retried = box.json("POST", f"/agent/runs/{pending['run_id']}/retry")
            checks = {"rule_fallback": intent_trace["fallback_used"],
                      "expected_intent_error": intent_trace["error_type"] == ("invalid_response" if kind == "unsafe_reply" else kind),
                      "template_fallback": reply.get("mode") == "fallback_template",
                      "expected_reply_error": reply.get("error") == kind,
                      "tool_facts_retained": "SF123456789" in order["final_response"],
                      "no_secret_in_result": "private-provider-body-must-not-leak" not in str(order) + str(completed),
                      "no_early_ticket": before == [], "customer_review_denied": denied.status_code == 403,
                      "ticket_persisted_once": len(business_db.list_tickets()) == 1,
                      "review_retry_same_run": completed["run_id"] == repeated["run_id"] == retried["run_id"],
                      "no_replay_model_calls": len(ledger.calls) == count,
                      "bounded_retries": all(c["attempt"] <= 2 for c in ledger.calls),
                      "not_claimed_generated": not reply.get("model_trace", {}).get("model_used")}
            rows.append({"id": "fault-" + kind, "input": "离线注入 " + kind, "passed": all(checks.values()),
                         "checks": checks, "error_type": kind, "latency_ms": sum(c["latency_ms"] for c in ledger.calls),
                         "execution_mode": "simulated_fault", "model_calls": ledger.summary()})
    return {"execution_mode": "simulated_fault", "cases": rows,
            "metrics": {"sample_count": len(rows), "passed": sum(r["passed"] for r in rows),
                        "actual_provider_calls": 0, "simulated_model_calls": sum(r["model_calls"]["actual_model_calls"] for r in rows)}}
