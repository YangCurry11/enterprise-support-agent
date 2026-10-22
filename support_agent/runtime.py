"""Durable run registry, checkpoint recovery, ownership and review audit.

SQLite profile supports one API worker. A process-wide lock serializes executions;
multi-worker deployments require a distributed lease and a PostgreSQL checkpointer.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from fastapi import HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from .agents import AgentState
from .auth import Principal
from .scoped_tools import ScopedTools
from .workflow import build_graph

execution_lock = threading.RLock()
logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self, data_dir: Path, tools_factory=ScopedTools):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = self.data_dir / "workflow_runs.db"
        self.checkpoints = self.data_dir / "workflow_checkpoints.db"
        self.tools_factory = tools_factory
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, input TEXT NOT NULL,
                    result TEXT, created_at TEXT NOT NULL,
                    UNIQUE(actor_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            if "conversation_id" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN conversation_id TEXT")
            if "context_json" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'")

    def initial_value(self, row):
        # thread_id 仍为 run_id；会话只提供有限、已冻结的辅助上下文。
        state = AgentState(row["input"], row["user_id"],
                           conversation_id=row.get("conversation_id"),
                           conversation_context=json.loads(row.get("context_json") or "{}"))
        return {"data": state.to_dict(), "run_id": row["run_id"]}

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.registry, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn

    def audit(self, run_id, actor, action, detail=None):
        with self.connection() as conn:
            conn.execute("INSERT INTO audit(run_id,actor_id,action,detail,created_at) VALUES (?,?,?,?,?)",
                         (run_id, actor, action, json.dumps(detail or {}, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))

    def row(self, run_id, principal):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row or (principal.role != "support" and row["user_id"] != principal.user_id):
            raise HTTPException(404, "运行不存在或不可访问")
        return dict(row)

    @contextmanager
    def graph(self, row):
        with SqliteSaver.from_conn_string(str(self.checkpoints)) as saver:
            yield build_graph(self.tools_factory(row["user_id"], row["run_id"]), saver)

    def render(self, graph, row):
        snapshot = graph.get_state({"configurable": {"thread_id": row["run_id"]}})
        result = dict(snapshot.values.get("data") or AgentState(row["input"], row["user_id"]).to_dict())
        pending = [item.value for task in snapshot.tasks for item in task.interrupts]
        status = "completed" if snapshot.values and not snapshot.next else "running"
        if pending:
            status = "awaiting_review" if pending[0]["kind"] == "approval" else "awaiting_input"
            result["final_response"] = pending[0]["message"]
        saved = json.loads(row["result"]) if row.get("result") else {}
        if status == "running" and saved.get("status") == "failed":
            status = "failed"
        result.update(run_id=row["run_id"], status=status, pending=pending, created_at=row["created_at"],
                      latency_ms=saved.get("latency_ms", 0), review=snapshot.values.get("review"))
        return result

    def invoke(self, graph, row, value, actor, action):
        started = time.perf_counter()
        try:
            graph.invoke(value, {"configurable": {"thread_id": row["run_id"]}, "recursion_limit": 20})
            result = self.render(graph, row)
            result["latency_ms"] = round((time.perf_counter() - started) * 1000)
            with self.connection() as conn:
                conn.execute("UPDATE runs SET result=? WHERE run_id=?", (json.dumps(result, ensure_ascii=False), row["run_id"]))
            self.audit(row["run_id"], actor, action, {"status": result["status"]})
            return result
        except Exception:
            logger.exception("Workflow execution failed run_id=%s", row["run_id"])
            with self.connection() as conn:
                conn.execute("UPDATE runs SET result=? WHERE run_id=?", (json.dumps({"status": "failed"}), row["run_id"]))
            self.audit(row["run_id"], actor, "execution_failed")
            raise HTTPException(503, "流程执行失败；可使用相同请求编号重试，不会重复创建工单。") from None

    def start(self, text, user_id, key, principal, *, conversation_id=None, context=None):
        fingerprint_values = [text, user_id] if conversation_id is None else [text, user_id, conversation_id]
        fingerprint = hashlib.sha256(json.dumps(fingerprint_values, ensure_ascii=False).encode()).hexdigest()
        with execution_lock:
            with self.connection() as conn:
                found = conn.execute("SELECT * FROM runs WHERE actor_id=? AND request_key=?", (principal.user_id, key)).fetchone()
                if found and found["fingerprint"] != fingerprint:
                    raise HTTPException(409, "相同请求编号不能用于不同请求")
                if not found:
                    run_id = str(uuid.uuid4())
                    conn.execute("INSERT INTO runs(run_id,actor_id,user_id,request_key,fingerprint,input,created_at,conversation_id,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (run_id, principal.user_id, user_id, key, fingerprint, text, datetime.now(timezone.utc).isoformat(),
                                  conversation_id, json.dumps(context or {}, ensure_ascii=False)))
                    found = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            row = dict(found)
            with self.graph(row) as graph:
                current = self.render(graph, row)
                if current["status"] not in {"running", "failed"}:
                    return current
                snapshot = graph.get_state({"configurable": {"thread_id": row["run_id"]}})
                value = None if snapshot.values else self.initial_value(row)
                return self.invoke(graph, row, value, principal.user_id, "run_started_or_recovered")

    def get(self, run_id, principal):
        with execution_lock:
            row = self.row(run_id, principal)
            with self.graph(row) as graph:
                return self.render(graph, row)

    def recover(self, run_id, principal):
        with execution_lock:
            row = self.row(run_id, principal)
            with self.graph(row) as graph:
                current = self.render(graph, row)
                if current["status"] not in {"running", "failed"}:
                    return current
                snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
                value = None if snapshot.values else self.initial_value(row)
                return self.invoke(graph, row, value, principal.user_id, "run_recovered")

    def resume(self, run_id, answer, principal, review=False):
        with execution_lock:
            row = self.row(run_id, principal)
            if review and principal.role != "support":
                raise HTTPException(403, "此操作需要客服审核权限")
            with self.graph(row) as graph:
                current = self.render(graph, row)
                if current["status"] == "completed" and review and current["review"]:
                    previous = current["review"]
                    if previous.get("approved") == answer["approved"]:
                        return current
                expected = "awaiting_review" if review else "awaiting_input"
                if current["status"] != expected:
                    raise HTTPException(409, "当前流程状态不允许此操作")
                if review:
                    answer = {**answer, "reviewer_id": principal.user_id}
                    self.audit(run_id, principal.user_id, "review_decision", answer)
                return self.invoke(graph, row, Command(resume=answer), principal.user_id, "run_resumed")

    def history(self, principal, limit):
        with self.connection() as conn:
            if principal.role == "support":
                rows = conn.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute("SELECT run_id FROM runs WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (principal.user_id, limit)).fetchall()
        return [self.get(row["run_id"], principal) for row in rows]

    def events(self, run_id, principal):
        self.row(run_id, principal)
        if principal.role != "support":
            raise HTTPException(403, "此操作需要客服审核权限")
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM audit WHERE run_id=? ORDER BY event_id", (run_id,))]

    def reviews(self, principal, limit=50, offset=0):
        if principal.role != "support":
            raise HTTPException(403, "此操作需要客服审核权限")
        with self.connection() as conn:
            rows = conn.execute("SELECT run_id FROM runs WHERE json_extract(result,'$.status')='awaiting_review' ORDER BY created_at LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [result for row in rows if (result := self.get(row["run_id"], principal))["status"] == "awaiting_review"]
