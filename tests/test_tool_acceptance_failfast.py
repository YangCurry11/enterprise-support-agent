"""Bounded three-turn acceptance stops on the first failed check; no network."""
import json
import os

import pytest
from langchain_core.messages import AIMessage

from evaluation import verify_tool_calling as verify
from evaluation.tool_calling_fakes import ScriptedQwen
from support_agent.model_runtime import CallLedger


@pytest.mark.parametrize("failed_turn,kind,attempts", [(1, "unsafe_reply", 2), (2, "unsafe_reply", 4),
                                                       (1, "payment", 2), (1, "approval", 2),
                                                       (1, "timeout", 1), (2, "timeout", 3)])
def test_first_failed_turn_stops_and_saves_diagnostics(tmp_path, monkeypatch, caplog, capsys, failed_turn, kind, attempts):
    marker = "private-rejected-reply-must-not-be-logged"
    class FailedTurn(ScriptedQwen):
        def invoke(self, messages):
            payload = json.loads(messages[1].content)
            selected = payload["intent"] == ("order_query" if failed_turn == 1 else "refund_policy")
            self.kind = kind if selected and kind not in {"payment", "approval"} else "normal"
            reply = super().invoke(messages)
            if selected and not reply.tool_calls:
                if kind in {"payment", "approval"}:
                    action = "支付已成功。" if kind == "payment" else "退款审批已通过。"
                    reply = AIMessage(content=reply.content + action)
                reply = AIMessage(content=reply.content + marker)
            return reply
    model = FailedTurn()
    monkeypatch.setattr(verify, "ScriptedQwen", lambda: model)
    assert verify.main(["--mode", "offline", "--max-model-calls", "8", "--output", str(tmp_path)]) == 1
    report = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    case = report["e2e"]["cases"][0]
    assert not case["passed"] and case["error_type"] == "acceptance_check_failed"
    assert case["failure_stage"] == f"turn_{failed_turn}" and case["stopped_after_turn"] == failed_turn
    assert len(case["results"]) == failed_turn and len(model.requests) == attempts
    assert report["model_calls"]["actual_model_calls"] == attempts
    assert all(c["attempt"] == 1 for c in report["model_calls"]["calls"])  # No extra retries.
    trace = case["results"][-1]["tool_calling_trace"]
    assert trace["error_type"] == ("timeout" if kind == "timeout" else "unsafe_reply") and trace["status"] == "fallback"
    if kind == "unsafe_reply":
        assert "unsupported_receipt_state" in trace["reply_validation"]["violations"]
        assert "unsupported_financial_action" in trace["reply_validation"]["violations"]
    if kind in {"payment", "approval"}:
        assert f"unsupported_{kind}_action" in trace["reply_validation"]["violations"]
    for name in ("latest.json", "details.csv", "manual_review.csv", "summary.md", "tool_review.json"):
        text = (tmp_path / name).read_text(encoding="utf-8-sig")
        assert marker not in text
        if name == "details.csv" and kind == "unsafe_reply":
            assert "unsupported_receipt_state" in text
    assert marker not in caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("budget,turn", [(1, 1), (3, 2)])
def test_all_turns_share_the_same_hard_budget_and_stop(budget, turn):
    ledger = CallLedger(budget, simulated=True)
    result = verify.verify(live=False, ledger=ledger)
    case = result["cases"][0]
    assert result["metrics"]["passed"] == 0
    assert len(case["results"]) == turn and case["failure_stage"] == f"turn_{turn}"
    assert case["results"][-1]["tool_calling_trace"]["error_type"] == "budget_exhausted"
    assert len(ledger.calls) == budget
    assert [c["call_id"] for c in ledger.calls] == list(range(1, budget + 1))
    node_ids = [i for r in case["results"] for c in r["tool_calling_trace"]["model_calls"]["calls"] for i in [c["call_id"]]]
    assert node_ids == list(range(1, budget + 1))


def test_fact_check_failure_stops_even_when_generation_flag_is_true(tmp_path, monkeypatch):
    original = verify.facts
    monkeypatch.setattr(verify, "facts", lambda result: ({"forced_failure": False}, [])
                        if result["intent"] == "order_query" else original(result))
    assert verify.main(["--mode", "offline", "--output", str(tmp_path)]) == 1
    r = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    case = r["e2e"]["cases"][0]
    assert len(case["results"]) == 1 and case["failure_stage"] == "turn_1"
    assert case["checks"]["turn_1_tool_model_generated"] and not case["checks"]["turn_1_facts"]


def test_third_turn_failure_does_not_run_replay_or_review(tmp_path, monkeypatch):
    from evaluation.sandbox import Sandbox
    original = Sandbox.message
    sent = []
    def corrupt(self, cid, text, key=None):
        sent.append(text)
        result = original(self, cid, text, key)
        if len(sent) == 3:
            result["tool_calling_trace"]["status"] = "unexpected_test_status"
        return result
    monkeypatch.setattr(Sandbox, "message", corrupt)
    assert verify.main(["--mode", "offline", "--output", str(tmp_path)]) == 1
    r = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    case = r["e2e"]["cases"][0]
    assert len(sent) == 3 and case["failure_stage"] == "turn_3"
    assert not case["checks"]["high_risk_guard"]
    assert "customer_cannot_approve" not in case["checks"]


def test_acceptance_uses_only_tfidf_and_never_calls_embedding(monkeypatch):
    from support_agent.embedding_client import EmbeddingClient
    from evaluation.evaluate_tool_calling import tool_environment
    def forbidden(*_a, **_k):
        pytest.fail("Acceptance cannot call Embedding")
    monkeypatch.setattr(EmbeddingClient, "embed", forbidden)
    # Pre-existing operator settings cannot enable Embedding in this isolated CLI.
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("RAG_MODE", "hybrid")
    with tool_environment(live=False):
        assert os.environ["EMBEDDING_ENABLED"] == "false" and os.environ["RAG_MODE"] == "tfidf"
        assert os.environ["LLM_MAX_RETRIES"] == "0" and os.environ["LLM_INTENT_ENABLED"] == "false"
    result = verify.verify(live=False, ledger=CallLedger(8, simulated=True))
    assert result["metrics"]["passed"] == 1
    assert result["model_calls"]["actual_model_calls"] == 4
