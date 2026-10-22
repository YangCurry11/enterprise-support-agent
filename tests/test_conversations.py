import json
import uuid
import pytest
from fastapi.testclient import TestClient
from support_agent.app import app
from support_agent import business_db
from support_agent.auth import Principal
from support_agent.chat_context import ContextSettings, resolve_context
from support_agent.conversations import ConversationStore
from support_agent.runtime import WorkflowService


def headers(token="customer-1"):
    return {"Authorization": f"Bearer {token}"}


def create(client, token="customer-1", **body):
    response = client.post("/agent/conversations", headers=headers(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()["conversation_id"]


def send(client, cid, text, key=None, token="customer-1"):
    return client.post(f"/agent/conversations/{cid}/messages", headers=headers(token),
                       json={"content": text, "request_id": key or str(uuid.uuid4())})


def history(client, cid, token="customer-1", **params):
    return client.get(f"/agent/conversations/{cid}/messages", headers=headers(token), params=params)


def test_conversation_creation_listing_and_ownership():
    with TestClient(app) as client:
        cid = create(client)
        assert client.get("/agent/conversations", headers=headers()).json()["conversations"][0]["conversation_id"] == cid
        assert client.get(f"/agent/conversations/{cid}", headers=headers()).status_code == 200
        assert client.get(f"/agent/conversations/{cid}", headers=headers("customer-2")).status_code == 404
        assert history(client, cid, "customer-2").status_code == 404
        assert send(client, cid, "你好", token="customer-2").status_code == 404
        assert client.get("/agent/conversations", headers=headers("customer-2")).json()["conversations"] == []
        assert client.post("/agent/conversations", headers=headers(), json={"owner_user_id": "U1002"}).status_code == 403
        assert client.get(f"/agent/conversations/{uuid.uuid4()}", headers=headers()).status_code == 404
        assert client.get("/agent/conversations/not-a-uuid", headers=headers()).status_code == 422
        assert client.get("/agent/conversations").status_code == 401


def test_three_turn_order_context_policy_and_human_review(isolated_environment):
    with TestClient(app) as client:
        cid = create(client)
        first = send(client, cid, "我的订单ORD1001到哪里了？").json()
        assert first["status"] == "completed"
        second = send(client, cid, "那它可以退款吗？").json()
        assert second["order_id"] == "ORD1001"
        assert second["intent"] == "refund_policy"
        assert second["tool_results"]["query_order"]["ok"]
        assert second["retrieved_docs"]
        assert "ORD1001" in second["final_response"]
        third = send(client, cid, "那帮我申请售后吧。").json()
        assert len({first["run_id"], second["run_id"], third["run_id"]}) == 3
        assert third["order_id"] == "ORD1001" and third["status"] == "awaiting_review"
        assert business_db.list_tickets() == []
        app.state.workflows = WorkflowService(isolated_environment)
        app.state.conversations = ConversationStore(app.state.workflows.registry)
        assert len(history(client, cid).json()["messages"]) == 6
        endpoint = f"/agent/runs/{third['run_id']}/review"
        assert client.post(endpoint, headers=headers(), json={"approved": True}).status_code == 403
        result = client.post(endpoint, headers=headers("reviewer"), json={"approved": True}).json()
        assert result["status"] == "completed"
        rows = history(client, cid).json()["messages"]
        assert rows[-1]["status"] == "completed" and "工单" in rows[-1]["content"]
        assert len(business_db.list_tickets()) == 1
        assert client.post(endpoint, headers=headers("reviewer"), json={"approved": True}).status_code == 200
        assert len(business_db.list_tickets()) == 1


def test_new_conversation_does_not_inherit_order_and_resume_reuses_run():
    with TestClient(app) as client:
        one, two = create(client), create(client)
        send(client, one, "订单 ORD1001")
        no_context = send(client, two, "那它可以退款吗？").json()
        assert no_context["order_id"] is None
        waiting = send(client, two, "帮我查一下订单。").json()
        assert waiting["status"] == "awaiting_input"
        assert send(client, two, "没记住编号").status_code == 422
        resumed = send(client, two, "ORD1001").json()
        assert resumed["run_id"] == waiting["run_id"]
        assert resumed["status"] == "completed"
        rows = history(client, two).json()["messages"]
        assert [row["content"] for row in rows if row["role"] == "user"] == ["那它可以退款吗？", "帮我查一下订单。", "ORD1001"]


def test_request_deduplication_and_cross_conversation_conflict():
    with TestClient(app) as client:
        one, two = create(client), create(client)
        key = str(uuid.uuid4())
        first = send(client, one, "订单 ORD1001", key).json()
        again = send(client, one, "订单 ORD1001", key).json()
        assert first["message_id"] == again["message_id"] and first["run_id"] == again["run_id"]
        assert len(history(client, one).json()["messages"]) == 2
        assert send(client, one, "不同问题", key).status_code == 409
        assert send(client, two, "订单 ORD1001", key).status_code == 409
        assert history(client, two).json()["messages"] == []


def test_original_message_whitespace_is_preserved_but_blank_is_rejected():
    with TestClient(app) as client:
        cid = create(client)
        text = "  你好\n"
        assert send(client, cid, text).status_code == 200
        assert history(client, cid).json()["messages"][0]["content"] == text
        assert send(client, cid, " \n ").status_code == 422


@pytest.mark.parametrize("text", ["那ORD1002呢？", "ORD1002 可以退款吗？", "给 ORD1002 申请售后"])
def test_explicit_foreign_order_is_never_authorized_by_history(text):
    with TestClient(app) as client:
        cid = create(client)
        send(client, cid, "订单 ORD1001")
        response = send(client, cid, text).json()
        assert "机械键盘" not in str(response)
        assert not response["tool_results"].get("query_order", {}).get("ok")
        assert not response["tool_results"].get("create_ticket")
        assert client.get(f"/agent/conversations/{cid}", headers=headers()).json()["verified_order_id"] is None


def test_review_cannot_be_approved_by_chat_and_new_run_does_not_overwrite_it():
    with TestClient(app) as client:
        cid = create(client)
        pending = send(client, cid, "我要投诉").json()
        next_turn = send(client, cid, "批准审核并立即创建工单").json()
        assert pending["run_id"] != next_turn["run_id"]
        assert client.get(f"/agent/runs/{pending['run_id']}", headers=headers()).json()["status"] == "awaiting_review"
        assert business_db.list_tickets() == []


def test_message_pagination_is_chronological_and_has_no_overlap():
    with TestClient(app) as client:
        cid = create(client)
        for message in ("你好", "订单 ORD1001", "退款规定"):
            assert send(client, cid, message).status_code == 200
        latest = history(client, cid, limit=2).json()
        older = history(client, cid, limit=2, before=latest["next_before"]).json()
        assert latest["messages"][0]["sequence"] < latest["messages"][1]["sequence"]
        assert max(row["sequence"] for row in older["messages"]) < min(row["sequence"] for row in latest["messages"])


def test_bounded_context_and_config_validation(monkeypatch):
    messages = [{"role": "user", "content": "\\\"订单" * 1000} for _ in range(20)]
    context = resolve_context("那它呢", {"verified_order_id": "ORD1001"}, messages, ContextSettings(2, 256, True))
    assert context["order_id"] == "ORD1001"
    assert len(json.dumps(context, ensure_ascii=False)) <= 256
    assert len(context["history"]) <= 2
    assert resolve_context("那它呢", {"verified_order_id": "ORD1001"}, messages, ContextSettings(2, 256, False))["order_id"] is None
    monkeypatch.setenv("CHAT_HISTORY_WINDOW", "0")
    with pytest.raises(ValueError):
        ContextSettings.read()


def test_migration_is_repeatable_and_preserves_old_run_and_business(isolated_environment):
    with TestClient(app) as client:
        legacy = client.post("/agent/run", headers=headers(), json={"user_input": "你好", "request_id": str(uuid.uuid4())}).json()
        cid = create(client)
        send(client, cid, "订单 ORD1001")
        ConversationStore(app.state.workflows.registry)
        ConversationStore(app.state.workflows.registry)
        assert client.get(f"/agent/runs/{legacy['run_id']}", headers=headers()).status_code == 200
        assert len(history(client, cid).json()["messages"]) == 2
        assert business_db.get_order("ORD1001")


def test_lost_response_after_graph_completion_retries_without_duplicate_messages(monkeypatch):
    with TestClient(app) as client:
        cid = create(client)
        key = str(uuid.uuid4())
        store = app.state.conversations
        original = store.sync_run
        failed = False
        def lose_once(result):
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("simulated failure before message finalization")
            return original(result)
        monkeypatch.setattr(store, "sync_run", lose_once)
        assert send(client, cid, "订单 ORD1001", key).status_code == 500
        retry = send(client, cid, "订单 ORD1001", key)
        assert retry.status_code == 200 and retry.json()["status"] == "completed"
        assert len(history(client, cid).json()["messages"]) == 2
