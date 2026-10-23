"""串行的隔离评测环境：真实应用/图/工具，临时 SQLite 与模拟身份。"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import json
import tempfile
import threading
import time
from unittest.mock import patch
import uuid

CUSTOMER = "eval-customer"
REVIEWER = "eval-reviewer"
OTHER = "eval-other"
_sandbox_lock = threading.RLock()


class Sandbox:
    def __init__(self, client, root, tool_calls):
        self.client, self.root, self.tool_calls = client, root, tool_calls
        self.requests = []

    def call(self, method, path, body=None, token=CUSTOMER):
        started = time.perf_counter()
        result = self.client.request(method, path, json=body, headers={"Authorization": "Bearer " + token})
        self.requests.append({"method": method, "path": path, "status_code": result.status_code,
                              "latency_ms": (time.perf_counter() - started) * 1000})
        return result

    def json(self, method, path, body=None, token=CUSTOMER):
        response = self.call(method, path, body, token)
        if not 200 <= response.status_code < 300:
            # 不带 HTTP body/原始异常；失败状态仍保存在 requests。
            raise RuntimeError("sandbox_http_" + str(response.status_code))
        return response.json()

    def conversation(self):
        return self.json("POST", "/agent/conversations", {})["conversation_id"]

    def message(self, cid, text, key=None):
        return self.json("POST", f"/agent/conversations/{cid}/messages",
                         {"content": text, "request_id": key or str(uuid.uuid4())})


@contextmanager
def sandbox(*, live=False, intent_live=False):
    from fastapi.testclient import TestClient
    from support_agent import config, business_db, app as api
    from support_agent.runtime import WorkflowService
    from support_agent.scoped_tools import ScopedTools
    tokens = json.dumps({CUSTOMER: {"user_id": "U1001", "role": "customer"},
                         OTHER: {"user_id": "U1002", "role": "customer"},
                         REVIEWER: {"user_id": "S1001", "role": "support"}})
    calls = []

    class ObservedTools(ScopedTools):
        def query_order(self, order_id):
            result = super().query_order(order_id)
            calls.append({"tool": "query_order", "input": order_id, "ok": result["ok"], "run_id": self.run_id})
            return result

        def search_policy(self, query, top_k=3):
            result = super().search_policy(query, top_k)
            calls.append({"tool": "search_policy", "ok": result["ok"], "run_id": self.run_id,
                          "sources": sorted({doc["source"] for doc in result.get("data", [])})})
            return result

        def create_ticket(self, **kwargs):
            result = super().create_ticket(**kwargs)
            calls.append({"tool": "create_ticket", "ok": result["ok"], "run_id": self.run_id})
            return result

    # patch 环境/模块仅适用于 CLI 单进程评测；不能挂到生产 API 并发执行。
    with _sandbox_lock, tempfile.TemporaryDirectory(prefix="serviceflow-phase2-") as directory, ExitStack() as stack:
        root = Path(directory)
        env = {"LLM_INTENT_ENABLED": "true" if intent_live else "false", "SUPPORT_AUTH_TOKENS": tokens,
               "SUPPORT_ENV": "development", "CHAT_CONTEXT_ENABLED": "true",
               "CHAT_HISTORY_WINDOW": "10", "CHAT_MAX_CONTEXT_CHARS": "12000"}
        if not live:
            env["LLM_API_KEY"] = ""
        stack.enter_context(patch.dict("os.environ", env))
        for module, name, value in ((config, "DATA_DIR", root), (business_db, "DATA_DIR", root),
                                    (business_db, "DB_PATH", root / "business.db"), (api, "DATA_DIR", root)):
            stack.enter_context(patch.object(module, name, value))
        previous = {key: getattr(api.app.state, key, None) for key in ("workflows", "conversations")}
        try:
            with TestClient(api.app) as client:
                api.app.state.workflows = WorkflowService(root, tools_factory=ObservedTools)
                yield Sandbox(client, root, calls)
        finally:
            for key, value in previous.items():
                setattr(api.app.state, key, value)
