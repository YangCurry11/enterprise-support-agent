import uuid
import pytest
from fastapi.testclient import TestClient
from support_agent.app import app
from support_agent import business_db
from support_agent.auth import Principal
from support_agent.runtime import WorkflowService
from support_agent.scoped_tools import ScopedTools


def headers(token="customer-1"):
    return {"Authorization": f"Bearer {token}"}


def start(client, text, key=None, token="customer-1", **kwargs):
    return client.post("/agent/run", headers=headers(token), json={
        "user_input": text, "request_id": key or str(uuid.uuid4()), **kwargs,
    })


def test_authentication_and_identity_enforcement():
    with TestClient(app) as client:
        assert client.get("/me").status_code == 401
        assert client.get("/me", headers=headers()).json()["user_id"] == "U1001"
        assert start(client, "你好", user_id="U1002").status_code == 403
        assert client.get("/orders/ORD1002", headers=headers()).status_code == 404
        assert client.post("/tickets", headers=headers(), json={}).status_code == 405


def test_order_workflow_and_tool_level_ownership():
    with TestClient(app) as client:
        own = start(client, "我的订单 ORD1001 到哪了？")
        assert own.status_code == 200
        assert own.json()["status"] == "completed"
        assert "SF123456789" in own.json()["final_response"]
        other = start(client, "ORD1002 到哪了？").json()
        assert not other["tool_results"]["query_order"]["ok"]
        assert "机械键盘" not in str(other)
        assert client.get(f"/agent/runs/{own.json()['run_id']}", headers=headers("customer-2")).status_code == 404


def test_clarification_checkpoint_survives_service_recreation(isolated_environment):
    with TestClient(app) as client:
        result = start(client, "我的订单到哪了？").json()
        assert result["status"] == "awaiting_input"
        app.state.workflows = WorkflowService(isolated_environment)
        response = client.post(f"/agent/runs/{result['run_id']}/resume", headers=headers(), json={"order_id": "ORD1001"})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert "SF123456789" in response.json()["final_response"]


@pytest.mark.parametrize("approved", [True, False])
def test_review_permissions_persistence_and_idempotency(approved, isolated_environment):
    with TestClient(app) as client:
        key = str(uuid.uuid4())
        result = start(client, "我要投诉", key).json()
        assert result["status"] == "awaiting_review"
        assert client.get("/agent/reviews", headers=headers()).status_code == 403
        assert client.get("/agent/reviews", headers=headers("reviewer")).json()["runs"][0]["run_id"] == result["run_id"]
        assert business_db.list_tickets() == []
        endpoint = f"/agent/runs/{result['run_id']}/review"
        assert client.post(endpoint, headers=headers(), json={"approved": True}).status_code == 403
        app.state.workflows = WorkflowService(isolated_environment)
        response = client.post(endpoint, headers=headers("reviewer"), json={"approved": approved, "note": "已核实"})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert client.get("/agent/reviews", headers=headers("reviewer")).json()["runs"] == []
        assert len(business_db.list_tickets()) == int(approved)
        assert start(client, "我要投诉", key).json()["run_id"] == result["run_id"]
        assert client.post(endpoint, headers=headers("reviewer"), json={"approved": approved}).status_code == 200
        assert len(business_db.list_tickets()) == int(approved)
        audit = client.get(f"/agent/runs/{result['run_id']}/audit", headers=headers("reviewer")).json()["events"]
        assert any(event["action"] == "review_decision" and event["actor_id"] == "S1001" for event in audit)


def test_request_key_conflict_history_isolation_and_input_validation():
    with TestClient(app) as client:
        key = str(uuid.uuid4())
        assert start(client, "你好", key).status_code == 200
        assert start(client, "不同问题", key).status_code == 409
        assert client.get("/agent/runs", headers=headers("customer-2")).json() == {"runs": []}
        assert client.get("/agent/runs?limit=0", headers=headers()).status_code == 422
        assert start(client, " ").status_code == 422
        assert start(client, "你好", role="support").status_code == 422
        assert client.options("/agent/run", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}).status_code == 200


def test_ticket_transaction_idempotency_and_payload_conflict():
    business_db.init_business_db()
    first = business_db.create_ticket("U1001", "complaint", "问题", idempotency_key="ticket-1")
    again = business_db.create_ticket("U1001", "complaint", "问题", idempotency_key="ticket-1")
    assert first == again
    with pytest.raises(ValueError):
        business_db.create_ticket("U1002", "complaint", "问题", idempotency_key="ticket-1")
    assert len(business_db.list_tickets()) == 1


def test_recover_after_ticket_write_before_node_checkpoint(isolated_environment):
    class LostReplyTools(ScopedTools):
        fail_once = True
        def create_ticket(self, **kwargs):
            result = super().create_ticket(**kwargs)
            if type(self).fail_once:
                type(self).fail_once = False
                raise TimeoutError("simulated lost response after commit")
            return result

    with TestClient(app) as client:
        app.state.workflows = WorkflowService(isolated_environment, tools_factory=LostReplyTools)
        key = str(uuid.uuid4())
        result = start(client, "我要投诉", key).json()
        response = client.post(f"/agent/runs/{result['run_id']}/review", headers=headers("reviewer"), json={"approved": True})
        assert response.status_code == 503
        assert len(business_db.list_tickets()) == 1
        app.state.workflows = WorkflowService(isolated_environment)
        assert client.get(f"/agent/runs/{result['run_id']}", headers=headers()).json()["status"] == "failed"
        recovered = client.post(f"/agent/runs/{result['run_id']}/retry", headers=headers())
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "completed"
        assert len(business_db.list_tickets()) == 1


def test_production_has_no_default_credentials(monkeypatch):
    from support_agent.auth import identities
    monkeypatch.delenv("SUPPORT_AUTH_TOKENS")
    monkeypatch.setenv("SUPPORT_ENV", "production")
    with pytest.raises(RuntimeError):
        identities()


def test_read_tool_transient_retry_and_no_foreign_ticket(isolated_environment):
    class FlakyRead(ScopedTools):
        attempts = 0
        def query_order(self, order_id):
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise TimeoutError("temporary transport error")
            return super().query_order(order_id)
    with TestClient(app) as client:
        app.state.workflows = WorkflowService(isolated_environment, tools_factory=FlakyRead)
        assert start(client, "ORD1001 到哪了？").json()["status"] == "completed"
        assert FlakyRead.attempts == 2
        blocked = start(client, "我要投诉 ORD1002").json()
        assert blocked["status"] == "completed"
        assert not blocked["tool_results"].get("create_ticket")
        assert business_db.list_tickets() == []


def test_migration_preserves_existing_ticket_and_is_repeatable():
    with business_db.get_connection() as conn:
        conn.execute("CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY,user_id TEXT,order_id TEXT,issue_type TEXT,description TEXT,priority TEXT,status TEXT,created_at TEXT)")
        conn.execute("INSERT INTO tickets(ticket_id,user_id) VALUES ('legacy-ticket','U1001')")
    business_db.init_business_db()
    business_db.init_business_db()
    assert business_db.list_tickets()[0]["ticket_id"] == "legacy-ticket"


def test_cli_facade_uses_same_workflow():
    from support_agent.agents import CustomerSupportAgent
    response = CustomerSupportAgent().run("我要投诉")
    assert response["status"] == "awaiting_review"
    assert business_db.list_tickets() == []


def test_model_failure_keeps_template(monkeypatch):
    from support_agent import llm_client
    monkeypatch.setenv("LLM_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(llm_client, "generate_customer_reply", lambda **kwargs: (_ for _ in ()).throw(TimeoutError("private-error")))
    with TestClient(app) as client:
        result = start(client, "ORD1001 到哪了？").json()
        assert "SF123456789" in result["final_response"]
        assert result["steps"][-1]["detail"]["mode"] == "fallback_template"
        assert "private-error" not in str(result)
