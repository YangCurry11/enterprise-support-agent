import json
from pathlib import Path
import shutil
import pytest
from evaluation import evaluate_tool_calling as evaluation
from evaluation import verify_tool_calling as verify


def test_fixed_cases_report_is_honest_reproducible_and_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "must-not-use-real-key")
    before = evaluation.DATASET.read_bytes()
    assert len(evaluation.load_cases()) == 36
    assert evaluation.main(["--mode", "offline", "--output", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    result = report["tool_calling"]
    assert result["metrics"]["passed"] == 36
    assert result["metrics"]["actual_provider_calls"] == 0
    assert result["model_calls"]["simulated"] is True
    assert result["model_calls"]["token_usage"] is None
    assert result["metrics"]["selection_accuracy"]["numerator"] < 36  # Deliberate wrong proposals were not repaired in metric.
    assert result["metrics"]["unauthorized_block_rate"] == {"numerator": 11, "denominator": 11, "value": 1.0}
    assert all(r["manual_review_status"] == "pending" for r in result["cases"])
    assert evaluation.DATASET.read_bytes() == before
    assert (tmp_path / "details.csv").is_file() and "NOT Qwen accuracy" in result["data_provenance"]
    for metric in ("selection_accuracy", "argument_validity", "execution_success", "workflow_completion", "fallback_rate"):
        item = result["metrics"][metric]
        assert item["value"] == item["numerator"] / item["denominator"]
    assert evaluation.summarize([])["selection_accuracy"]["value"] is None


def test_new_three_turn_cli_uses_real_services_but_no_provider(tmp_path):
    assert verify.main(["--mode", "offline", "--output", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert report["e2e"]["metrics"]["passed"] == 1
    assert report["model_calls"]["actual_model_calls"] == 4 and report["model_calls"]["simulated"]
    assert len(report["e2e"]["cases"][0]["results"]) == 3
    assert report["e2e"]["cases"][0]["results"][-1]["status"] == "awaiting_review"
    assert (tmp_path / "tool_review.json").is_file()
    assert "tool_model_generated" in (tmp_path / "manual_review.csv").read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("args", [["--mode", "live"], ["--mode", "live", "--allow-remote"],
    ["--mode", "live", "--max-model-calls", "6"], ["--mode", "live", "--allow-remote", "--max-model-calls", "9"]])
def test_live_gate_refuses_without_explicit_bounded_authorization(args, monkeypatch):
    monkeypatch.setattr(verify, "verify", lambda **_k: pytest.fail("must not reach execution"))
    with pytest.raises(SystemExit) as exc:
        verify.main(args)
    assert exc.value.code == 2


def test_synthetic_manifest_fails_closed_before_data_transfer(tmp_path):
    assert verify.check_synthetic_sources()["synthetic_fixture_matches"]
    shutil.copytree(verify.ROOT / "data/policies", tmp_path / "data/policies")
    for name in ("users.json", "orders.json"):
        shutil.copy2(verify.ROOT / "data" / name, tmp_path / "data" / name)
    assert verify.check_synthetic_sources(tmp_path)["synthetic_fixture_matches"]
    (tmp_path / "data/policies/customer-private.md").write_text("private", encoding="utf-8")
    with pytest.raises(ValueError, match="file set changed"):
        verify.check_synthetic_sources(tmp_path)
    (tmp_path / "data/policies/customer-private.md").unlink()
    (tmp_path / "data/orders.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="fixture changed"):
        verify.check_synthetic_sources(tmp_path)


def test_live_preflight_prints_boolean_not_key_and_sends_nothing(monkeypatch, capsys):
    from support_agent.model_runtime import ModelSettings
    settings = ModelSettings("do-not-print-this-key", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-offline-test", 20, .2, 0, False)
    monkeypatch.setattr(ModelSettings, "read", lambda: settings)
    monkeypatch.setattr(verify, "verify", lambda **_k: pytest.fail("preflight cannot execute"))
    assert verify.main(["--check-config"]) == 0
    out = capsys.readouterr().out
    assert "do-not-print-this-key" not in out
    assert json.loads(out)["network_calls"] == 0 and json.loads(out)["configuration"]["key_configured"] is True
