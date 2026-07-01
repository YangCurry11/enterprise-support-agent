# 模拟企业内部业务 API 客户端 （负责和后端接口说话的人）
from __future__ import annotations

from typing import Any, Dict, Optional
import requests

from .config import BUSINESS_API_URL # 导入API地址


class BusinessAPIError(RuntimeError): # 自定义错误类
    """业务 API 调用错误。"""


class BusinessAPIClient: # 业务 API 客户端类
    """模拟企业内部业务 API 客户端。真实工作中这里会对接订单、CRM、工单等系统。"""

    def __init__(self, base_url: str = BUSINESS_API_URL, timeout: int = 10):
        self.base_url = base_url.rstrip("/") # .rstrip("/")去除末尾的斜杠
        self.timeout = timeout # 超时时间默认10s

    def _get(self, path: str) -> Dict[str, Any]: # _get方法用于发送GET请求
        url = f"{self.base_url}{path}" # 拼接完整的URL
        # 错误处理 try-except 语句  
        try: 
            resp = requests.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BusinessAPIError(f"无法连接业务 API：{exc}") from exc
        # 状态码判断
        if resp.status_code >= 400:
            raise BusinessAPIError(f"业务 API 返回错误 {resp.status_code}: {resp.text}")
        return resp.json() # 将API结果转为Python字典

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BusinessAPIError(f"无法连接业务 API：{exc}") from exc

        if resp.status_code >= 400:
            raise BusinessAPIError(f"业务 API 返回错误 {resp.status_code}: {resp.text}")
        return resp.json()

    # 查询订单
    def query_order(self, order_id: str) -> Dict[str, Any]:
        return self._get(f"/orders/{order_id}")
    # 查询用户
    def query_user(self, user_id: str) -> Dict[str, Any]:
        return self._get(f"/users/{user_id}")
    # 创建工单
    def create_ticket(
        self,
        user_id: str,
        issue_type: str,
        description: str,
        order_id: Optional[str] = None,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "issue_type": issue_type,
            "description": description,
            "order_id": order_id,
            "priority": priority,
        }
        return self._post("/tickets", payload)
# 获取全部政策列表
    def list_policies(self):
        return self._get("/policies")
# 获取指定政策详情
    def get_policy(self, policy_name: str):
        return self._get(f"/policies/{policy_name}")
