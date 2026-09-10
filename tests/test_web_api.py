from fastapi.testclient import TestClient

from support_agent.mock_api import app


def test_vue_origin_is_allowed():
    with TestClient(app) as client:
        response = client.options("/agent/run", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_agent_endpoint_runs_complete_workflow(monkeypatch):
    expected = {
        "user_input": "你好",
        "user_id": "U1001",
        "intent": "chitchat",
        "final_response": "您好",
        "steps": [],
        "tool_results": {},
        "retrieved_docs": [],
        "need_human": False,
        "latency_ms": 1,
    }

    class FakeAgent:
        def run(self, user_input, user_id):
            assert user_input == "你好"
            assert user_id == "U1001"
            return expected

    monkeypatch.setattr("support_agent.mock_api.CustomerSupportAgent", FakeAgent)
    with TestClient(app) as client:
        response = client.post("/agent/run", json={"user_input": "你好", "user_id": "U1001"})
    assert response.status_code == 200
    assert response.json() == expected


def test_agent_endpoint_validates_input():
    with TestClient(app) as client:
        assert client.post("/agent/run", json={"user_input": "   "}).status_code == 422
        assert client.post("/agent/run", json={"user_input": " " * 1001}).status_code == 422
        assert client.post("/agent/run", json={"user_input": "你好", "role": "admin"}).status_code == 422
        assert client.get("/agent/runs?limit=0").status_code == 422


def test_history_endpoint(monkeypatch):
    monkeypatch.setattr("support_agent.mock_api.list_agent_runs", lambda limit: [{"run_id": "run-1"}])
    with TestClient(app) as client:
        response = client.get("/agent/runs?limit=5")
    assert response.json() == {"runs": [{"run_id": "run-1"}]}
