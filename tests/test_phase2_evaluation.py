import hashlib
import json
import os
from pathlib import Path
import socket
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from support_agent import llm_client
from support_agent.model_runtime import CallLedger, model_calls
from evaluation.run_evaluation import main, load
from evaluation.verify_qwen import verify, main as verify_main
from evaluation.evaluators import intent_eval, reply_eval
from evaluation import failure_checks


class ScriptedModel(RunnableLambda):
    """只有离线测试使用，保留图、链与解析接口，不是真实千问。"""
    def __init__(self):
        def reply(value):
            text = str(value)
            content = "订单 ORD1001 当前状态已发货，商品无线蓝牙耳机，顺丰物流单号 SF123456789，预计2天内送达。"
            if "refund_policy" in text:
                content += "依据 refund_policy.md，需要结合签收日期及商品情况审核，不代表退款已批准。"
            return AIMessage(content=content, usage_metadata={"input_tokens":10,"output_tokens":20,"total_tokens":30})
        super().__init__(reply)

    def with_structured_output(self, *_args, **_kwargs):
        def classify(messages):
            text = messages[-1][1]
            decision = llm_client.IntentDecision(intent="refund_policy" if "退" in text else "order_query", reason="模拟输出")
            return {"raw":AIMessage(content="", usage_metadata={"input_tokens":3,"output_tokens":2,"total_tokens":5}),
                    "parsed":decision, "parsing_error":None}
        return RunnableLambda(classify)


@pytest.fixture
def simulated_model(monkeypatch):
    for key, value in {"LLM_API_KEY":"offline-placeholder-do-not-publish", "LLM_BASE_URL":"https://offline.invalid/v1",
                       "LLM_MODEL":"offline-scripted-model", "LLM_TIMEOUT_SECONDS":"0.1", "LLM_TEMPERATURE":"0.2",
                       "LLM_MAX_RETRIES":"0", "LLM_INTENT_ENABLED":"true"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setattr(llm_client, "get_llm", lambda: ScriptedModel())
    monkeypatch.setattr("evaluation.run_evaluation.CallLedger", lambda limit: CallLedger(limit, simulated=True))
    monkeypatch.setattr("evaluation.verify_qwen.CallLedger", lambda limit: CallLedger(limit, simulated=True))
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network_forbidden")))


def test_same_cases_rule_baseline_raw_model_and_guard_are_separate(simulated_model):
    ledger = CallLedger(3, simulated=True)
    cases = [{"id":"model-difference","text":"啥时候能收到呀","intent":"order_query"},
             {"id":"high-risk","text":"我要投诉","intent":"complaint"}]
    with model_calls(ledger):
        report = intent_eval.evaluate(cases, live=True)
    assert report["rule_baseline"]["sample_count"] == report["metrics"]["sample_count"] == 2
    first, second = report["cases"]
    assert first["rule_prediction"] == "unknown"
    assert first["final_prediction"] == first["model_prediction"] == "order_query"
    assert second["guard_applied"] and second["model_prediction"] is None and not second["model_used"]
    assert report["metrics"]["actual_model_calls"] == 1
    assert report["raw_model_metrics"]["sample_count"] == 1


def test_all_reply_scenarios_offline_and_failures_are_explicit(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network_forbidden")))
    report = reply_eval.evaluate(load("reply_cases.jsonl"))
    assert report["metrics"]["passed"] == report["metrics"]["sample_count"] == 6, report
    assert report["metrics"]["generated_reply_count"] == 0
    assert report["metrics"]["manual_reviewed"] == 0
    assert all(row["execution_mode"] == "offline" and row["manual_review_status"] == "pending" for row in report["cases"])
    faults = failure_checks.evaluate()
    assert faults["metrics"]["passed"] == faults["metrics"]["sample_count"] == 6, faults
    assert faults["metrics"]["actual_provider_calls"] == 0
    assert all(row["model_calls"]["simulated"] for row in faults["cases"])


def test_live_reply_budget_exhaustion_is_retained_as_failed_case(simulated_model):
    ledger = CallLedger(1, simulated=True)
    with model_calls(ledger):
        report = reply_eval.evaluate([load("reply_cases.jsonl")[3]], live=True)
    row = report["cases"][0]
    assert not row["passed"] and not row["checks"]["expected_live_replies_generated"]
    assert row["fallback_used"] and row["error_type"] == "budget_exhausted"
    assert len(ledger.calls) == 1


@pytest.mark.parametrize("limit,passed", [(8,1), (2,0)])
def test_three_turn_uses_real_graph_sqlite_original_review_and_hard_budget(simulated_model, limit, passed):
    ledger = CallLedger(limit, simulated=True)
    report = verify(live=True, ledger=ledger)
    assert report["metrics"]["passed"] == passed, report
    row = report["cases"][0]
    assert row["checks"]["same_run_after_resume"] and row["checks"]["six_persistent_messages"]
    assert row["checks"]["exactly_one_ticket"] and row["checks"]["no_replay_model_calls"]
    assert len(ledger.calls) == min(4, limit)  # 两轮 intent+reply；第三轮 review_guard 与批准结果确定性
    assert all(call["simulated"] for call in ledger.calls)


def test_legacy_live_cli_keeps_intent_only_and_counts_physical_calls(simulated_model, tmp_path):
    assert main(["--mode","live","--live-limit","5","--output",str(tmp_path)]) == 0
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert report["live_components"] == ["intent"]
    assert report["reply"]["execution_mode"] == "not_requested"
    assert report["model_calls"]["actual_model_calls"] == 5
    assert all(row["operation"] == "intent" for row in report["model_calls"]["calls"])
    assert report["workflow"]["execution_mode"] == report["rag"]["execution_mode"] == "offline"
    summary = (tmp_path/"summary.md").read_text(encoding="utf-8")
    assert "同批规则基线" in summary and "原始模型成功子集" in summary
    assert "confusion_matrix" not in summary  # 完整矩阵在JSON，摘要不堆砌原始JSON


def test_explicit_reply_component_does_not_enable_live_intent(simulated_model, tmp_path):
    assert main(["--mode","live","--components","reply","--reply-limit","1","--max-model-calls","1","--output",str(tmp_path)]) == 0
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert report["live_components"] == ["reply"]
    assert report["intent"]["execution_mode"] == "offline"
    assert [row["operation"] for row in report["model_calls"]["calls"]] == ["reply"]
    assert report["reply"]["metrics"]["passed"] == 1
    assert (tmp_path/"manual_review.csv").read_text(encoding="utf-8-sig").count("pending") == 1


def test_combined_components_share_budget_and_keep_fallback_failure(simulated_model, tmp_path):
    result = main(["--mode","live","--components","intent,reply","--live-limit","1","--reply-limit","1",
                   "--max-model-calls","1","--output",str(tmp_path)])
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert result == 1
    assert report["live_components"] == ["intent","reply"]
    assert report["model_calls"]["actual_model_calls"] == 1 and report["model_calls"]["simulated"]
    assert [row["operation"] for row in report["model_calls"]["calls"]] == ["intent"]
    assert report["reply"]["cases"][0]["error_type"] == "budget_exhausted"
    assert not report["reply"]["cases"][0]["passed"]


@pytest.mark.parametrize("argv", [
    ["--mode","live","--components","reply"], ["--components","e2e"], ["--components","intent,intent"],
    ["--max-model-calls","0"], ["--max-model-calls","501"], ["--reply-limit","0"], ["--live-limit","81"],
])
def test_cli_rejects_implicit_expansion_or_invalid_limits(argv, simulated_model):
    with pytest.raises(SystemExit) as error:
        main(argv)
    assert error.value.code == 2


def test_live_e2e_requires_explicit_budget(simulated_model):
    with pytest.raises(SystemExit) as error:
        verify_main(["--mode","live"])
    assert error.value.code == 2


def test_preflight_is_redacted_no_network_and_never_creates_client(simulated_model, monkeypatch, capsys):
    monkeypatch.setattr(llm_client, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("must_not_create_client")))
    assert main(["--check-config"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["network_calls"] == 0 and output["configuration"]["key_configured"]
    assert "offline-placeholder" not in json.dumps(output)


def test_new_offline_entry_does_not_modify_original_files_or_environment(tmp_path, monkeypatch):
    from support_agent import business_db, config, app as api
    root = Path(__file__).resolve().parents[1]
    private_files = [p for p in [root/".env", *list((root/"data").glob("*.db"))] if p.is_file()]
    before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in private_files}
    db_before, data_before, api_before = business_db.DB_PATH, config.DATA_DIR, api.DATA_DIR
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network_forbidden")))
    monkeypatch.setenv("LLM_API_KEY", "offline-must-ignore-this-key")
    assert verify_main(["--output",str(tmp_path)]) == 0
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert report["mode"] == "offline" and report["model_calls"]["actual_model_calls"] == 0
    assert report["e2e"]["metrics"]["passed"] == 1
    assert business_db.DB_PATH == db_before and config.DATA_DIR == data_before and api.DATA_DIR == api_before
    assert os.environ["LLM_API_KEY"] == "offline-must-ignore-this-key"
    assert before == {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in private_files}


def test_missing_model_preflight_exits_without_creating_client(simulated_model, monkeypatch, capsys):
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setattr(llm_client, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("client_forbidden")))
    with pytest.raises(SystemExit) as error:
        main(["--check-config"])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "LLM_MODEL" in output and "offline-placeholder" not in output


def test_csv_formula_protection_keeps_json_original(tmp_path):
    from evaluation.run_evaluation import write_artifact, csv_safe
    assert csv_safe(" =HYPERLINK('example')").startswith("'")
    assert csv_safe("normal") == "normal" and csv_safe(3) == 3
    report = {"mode":"offline", "generated_at":"2026-10-23", "reply":{"metrics":{"sample_count":1}, "cases":[{
        "id":"case-1", "input":"=1+1", "passed":True, "latency_ms":0,
        "results":[{"run_id":"test-run", "final_response":"=1+1", "steps":[]}]}]}}
    write_artifact(report, tmp_path)
    assert "'=1+1" in (tmp_path/"manual_review.csv").read_text(encoding="utf-8-sig")
    assert json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))["reply"]["cases"][0]["input"] == "=1+1"
