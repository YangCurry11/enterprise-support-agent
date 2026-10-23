"""Tools enforce customer ownership even when called outside an HTTP endpoint."""
from __future__ import annotations
from functools import lru_cache
from . import business_db
from .rag import PolicyKnowledgeBase
from .order_facts import build_order_facts


@lru_cache(maxsize=1)
def policy_index():
    return PolicyKnowledgeBase()


class ScopedTools:
    def __init__(self, user_id: str, run_id: str):
        self.user_id = user_id
        self.run_id = run_id

    def query_order(self, order_id: str):
        order = business_db.get_order(order_id)
        if not order or order["user_id"] != self.user_id:
            return {"ok": False, "error": "订单不存在或当前用户不可访问", "code": "order_unavailable"}
        return {"ok": True, "data": order, "facts": build_order_facts(order).model_dump()}

    def search_policy(self, query: str, top_k: int = 3):
        return {"ok": True, "data": policy_index().search(query, top_k=top_k)}

    def create_ticket(self, user_id: str, issue_type: str, description: str,
                      order_id: str | None = None, priority: str = "normal"):
        if user_id != self.user_id or (order_id and not self.query_order(order_id)["ok"]):
            return {"ok": False, "error": "工单所属用户或订单不可访问", "code": "forbidden"}
        return {"ok": True, "data": business_db.create_ticket(
            user_id=user_id, issue_type=issue_type, description=description,
            order_id=order_id, priority=priority, idempotency_key=f"{self.run_id}:ticket")}
