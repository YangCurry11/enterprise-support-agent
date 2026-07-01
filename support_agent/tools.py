# 把 API 调用和知识库检索封装成 Agent 可用工具。
from __future__ import annotations

from typing import Dict, Optional

from .api_client import BusinessAPIClient, BusinessAPIError
from .rag import PolicyKnowledgeBase # 导入政策知识库


class SupportTools:
    """Agent 可调用的工具集合。"""

    def __init__(self, api_client: Optional[BusinessAPIClient] = None, kb: Optional[PolicyKnowledgeBase] = None):
        self.api = api_client or BusinessAPIClient() # 如果外面没有传入api_client，则默认创建的BusinessAPIClient
        self.kb = kb or PolicyKnowledgeBase()

    def query_order(self, order_id: str) -> Dict:
        """查询订单状态。"""
        try:
            data = self.api.query_order(order_id)
            return {"ok": True, "data": data}
        except BusinessAPIError as exc:
            return {"ok": False, "error": str(exc)}

    def query_user(self, user_id: str) -> Dict:
        """查询用户信息。"""
        try:
            data = self.api.query_user(user_id)
            return {"ok": True, "data": data}
        except BusinessAPIError as exc:
            return {"ok": False, "error": str(exc)}

    def create_ticket(self, user_id: str, issue_type: str, description: str, order_id: str | None = None, priority: str = "normal") -> Dict:
        """创建售后/投诉/物流异常工单。"""
        try:
            data = self.api.create_ticket(
                user_id=user_id,
                issue_type=issue_type,
                description=description,
                order_id=order_id,
                priority=priority,
            )
            return {"ok": True, "data": data}
        except BusinessAPIError as exc:
            return {"ok": False, "error": str(exc)}

    def search_policy(self, query: str, top_k: int = 3) -> Dict:
        """检索退款、物流、售后等政策知识库。"""
        docs = self.kb.search(query, top_k=top_k)
        return {"ok": True, "data": docs}
