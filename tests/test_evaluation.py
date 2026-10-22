import json
import socket
import pytest
from fastapi.testclient import TestClient
from support_agent.app import app
from evaluation.evaluators.metrics import classification_metrics, percentile, retrieval_metrics
from evaluation.run_evaluation import load, main


def test_metric_math_and_empty_inputs():
    result = classification_metrics(["unknown", "order_query"], ["unknown", "unknown"])
    assert result["accuracy"] == .5
    assert result["per_class"]["unknown"]["precision"] == .5
    assert result["confusion_matrix"][0][7] == 1
    assert percentile(list(range(1, 101)), .95) == 95
    assert percentile([8, 2, 5], .5) == 5
    assert percentile([], .95) is None
    assert classification_metrics([], [])["accuracy"] is None
    with pytest.raises(ValueError):
        classification_metrics(["unknown"], [])
    retrieval = retrieval_metrics([{"gold_sources": ["a"], "retrieved_sources": ["b", "a"], "latency_ms": 2}])
    assert retrieval["recall_at_1"] == 0 and retrieval["recall_at_3"] == 1 and retrieval["mrr"] == .5


def test_datasets_are_unique_traceable_and_not_claimed_human_annotated():
    for name in ("intent_cases.jsonl", "rag_cases.jsonl", "workflow_cases.jsonl"):
        rows = load(name)
        assert len({r["id"] for r in rows}) == len(rows)
        assert all("pending" in row["annotation_source"] for row in rows)
    assert len(load("intent_cases.jsonl")) >= 80


def test_offline_evaluation_has_no_network_and_writes_reproducible_report(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Offline evaluation must not access network")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key-offline-must-ignore")
    assert main(["--mode", "offline", "--output", str(tmp_path)]) == 0
    report = json.loads((tmp_path/"latest.json").read_text(encoding="utf-8"))
    assert report["mode"] == "offline" and report["live_components"] == []
    assert report["intent"]["metrics"]["sample_count"] >= 80
    assert report["workflow"]["metrics"]["passed"] == 10
    assert report["workflow"]["metrics"]["request_total"] == report["workflow"]["metrics"]["request_success"] + report["workflow"]["metrics"]["request_failed"]
    assert report["workflow"]["metrics"]["token_usage"] is None
    assert (tmp_path/"details.csv").is_file() and (tmp_path/"summary.md").is_file()


def test_evaluation_report_is_reviewer_only_and_empty_is_honest(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/agent/evaluations/latest").status_code == 401
        assert client.get("/agent/evaluations/latest", headers={"Authorization": "Bearer customer-1"}).status_code == 403
        assert client.get("/agent/evaluations/latest", headers={"Authorization": "Bearer reviewer"}).json() == {"report": None}
        (tmp_path/"latest.json").write_text("invalid", encoding="utf-8")
        assert client.get("/agent/evaluations/latest", headers={"Authorization": "Bearer reviewer"}).status_code == 503
