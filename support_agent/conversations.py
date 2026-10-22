"""会话与消息持久化；不替换 LangGraph run/thread_id。

先事务登记消息对和固定调度信息，再执行可重入的工作流，最后事务更新结果。
跨检查点与业务写入不声称分布式恰好一次，丢响应后沿用 request_id 重试。
"""
from __future__ import annotations
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from fastapi import HTTPException
from . import business_db
from .chat_context import ContextSettings, resolve_context
from .intent import extract_order_id
from .runtime import execution_lock


def now():
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chat_schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations(
                    conversation_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_message_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active', verified_order_id TEXT,
                    verified_order_sequence INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS conversation_owner_time ON conversations(owner_user_id, updated_at);
                CREATE TABLE IF NOT EXISTS conversation_messages(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id), run_id TEXT,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), content TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS conversation_message_order ON conversation_messages(conversation_id, sequence);
                CREATE INDEX IF NOT EXISTS conversation_message_run ON conversation_messages(run_id);
                CREATE TABLE IF NOT EXISTS conversation_requests(
                    actor_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
                    user_message_id TEXT NOT NULL UNIQUE, assistant_message_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL, dispatch TEXT NOT NULL, run_id TEXT, status TEXT NOT NULL,
                    PRIMARY KEY(actor_id, request_id));
            """)
            conn.execute("INSERT OR IGNORE INTO chat_schema_migrations VALUES (1,?)", (now(),))

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn

    def get(self, conversation_id, principal):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
        if not row or (principal.role != "support" and row["owner_user_id"] != principal.user_id):
            raise HTTPException(404, "会话不存在或不可访问")
        return dict(row)

    def create(self, principal, title="新会话", owner_user_id=None):
        owner = owner_user_id or principal.user_id
        if principal.role != "support" and owner != principal.user_id:
            raise HTTPException(403, "不能为其他用户创建会话")
        if not business_db.get_user(owner):
            raise HTTPException(404, "服务对象不存在，客服身份请指定客户编号")
        identifier, stamp = str(uuid.uuid4()), now()
        with self.connection() as conn:
            conn.execute("INSERT INTO conversations(conversation_id,owner_user_id,title,created_at,updated_at) VALUES (?,?,?,?,?)",
                         (identifier, owner, title, stamp, stamp))
        return self.get(identifier, principal)

    def list(self, principal, limit=30, offset=0):
        with self.connection() as conn:
            where, params = ("", []) if principal.role == "support" else (" WHERE owner_user_id=?", [principal.user_id])
            rows = conn.execute("SELECT * FROM conversations" + where + " ORDER BY updated_at DESC,conversation_id LIMIT ? OFFSET ?",
                                [*params, limit, offset]).fetchall()
        return [dict(row) for row in rows]

    def messages(self, conversation_id, principal, limit=50, before=None):
        self.get(conversation_id, principal)
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id=? AND sequence<? ORDER BY sequence DESC LIMIT ?",
                                (conversation_id, before or 9223372036854775807, limit)).fetchall()
        result = [dict(row) for row in reversed(rows)]
        for row in result:
            row["metadata"] = json.loads(row["metadata"])
        return result

    def sync_run(self, result):
        with self.connection() as conn:
            requests = conn.execute("SELECT r.*,m.sequence FROM conversation_requests r JOIN conversation_messages m ON m.message_id=r.user_message_id WHERE r.run_id=? ORDER BY m.sequence",
                                    (result["run_id"],)).fetchall()
            if not requests:
                return
            latest = requests[-1]
            saved = conn.execute("SELECT content,status,metadata FROM conversation_messages WHERE message_id=?", (latest["assistant_message_id"],)).fetchone()
            encoded = json.dumps({"result": result}, ensure_ascii=False)
            if saved["content"] == result["final_response"] and saved["status"] == result["status"] and saved["metadata"] == encoded:
                return
            # 原始用户文字与历史澄清提示不改写；仅最新回复更新为审核/恢复后的结果。
            conn.execute("UPDATE conversation_messages SET content=?,status=?,metadata=? WHERE message_id=?",
                         (result["final_response"], result["status"], encoded, latest["assistant_message_id"]))
            conn.execute("UPDATE conversation_messages SET status=? WHERE run_id=?", (result["status"], result["run_id"]))
            conn.execute("UPDATE conversation_requests SET status=? WHERE run_id=?", (result["status"], result["run_id"]))
            order = result.get("tool_results", {}).get("query_order", {})
            context = json.loads(latest["dispatch"]).get("context", {})
            if order.get("ok") or context.get("order_source") == "explicit":
                verified = order["data"]["order_id"] if order.get("ok") else None
                conn.execute("UPDATE conversations SET verified_order_id=?,verified_order_sequence=? WHERE conversation_id=? AND verified_order_sequence<=?",
                             (verified, latest["sequence"], latest["conversation_id"], latest["sequence"]))
            conn.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (now(), latest["conversation_id"]))


class ConversationService:
    def __init__(self, store, workflows):
        self.store, self.workflows = store, workflows

    def reconcile(self, conversation_id, principal):
        self.store.get(conversation_id, principal)
        with self.store.connection() as conn:
            run_ids = [row[0] for row in conn.execute("SELECT DISTINCT run_id FROM conversation_requests WHERE conversation_id=? AND run_id IS NOT NULL", (conversation_id,))]
        for run_id in run_ids:
            # 仅读取检查点，不 invoke，加载历史绝不会重新执行建单。
            self.store.sync_run(self.workflows.get(run_id, principal))

    def send(self, conversation_id, content, request_id, principal):
        with execution_lock:
            conversation = self.store.get(conversation_id, principal)
            with self.store.connection() as conn:
                request = conn.execute("SELECT * FROM conversation_requests WHERE actor_id=? AND request_id=?", (principal.user_id, request_id)).fetchone()
            if request:
                if request["conversation_id"] != conversation_id or request["content"] != content:
                    raise HTTPException(409, "相同请求编号不能用于不同消息或会话")
                request = dict(request)
                if request["status"] not in {"pending", "failed"}:
                    result = self.workflows.get(request["run_id"], principal)
                    self.store.sync_run(result)
                    return self.envelope(request, result)
            else:
                self.reconcile(conversation_id, principal)
                conversation = self.store.get(conversation_id, principal)
                with self.store.connection() as conn:
                    if conn.execute("SELECT 1 FROM conversation_requests WHERE conversation_id=? AND status IN ('pending','failed')", (conversation_id,)).fetchone():
                        raise HTTPException(409, "上一条消息尚未完成，请先沿用原请求重试或恢复")
                    waiting = conn.execute("SELECT DISTINCT run_id FROM conversation_requests WHERE conversation_id=? AND status='awaiting_input'", (conversation_id,)).fetchall()
                    collision = conn.execute("SELECT 1 FROM runs WHERE actor_id=? AND request_key=?", (principal.user_id, request_id)).fetchone()
                    if collision:
                        raise HTTPException(409, "该请求编号已用于其他业务请求")
                if len(waiting) > 1:
                    raise HTTPException(409, "有多条待补充请求，请从运行详情选择要继续的请求")
                context = resolve_context(content, conversation, self.store.messages(conversation_id, principal, ContextSettings.read().window))
                dispatch = {"operation": "start", "context": context}
                if waiting:
                    order = extract_order_id(content)
                    if not order:
                        raise HTTPException(422, "请先补充当前请求的订单号，例如 ORD1001")
                    dispatch.update(operation="resume", run_id=waiting[0]["run_id"], order_id=order)
                stamp = now()
                request = {"actor_id": principal.user_id, "request_id": request_id, "conversation_id": conversation_id,
                           "user_message_id": str(uuid.uuid4()), "assistant_message_id": str(uuid.uuid4()),
                           "content": content, "dispatch": json.dumps(dispatch, ensure_ascii=False), "run_id": dispatch.get("run_id"), "status": "pending"}
                with self.store.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("INSERT INTO conversation_requests VALUES (:actor_id,:request_id,:conversation_id,:user_message_id,:assistant_message_id,:content,:dispatch,:run_id,:status)", request)
                    for role in ("user", "assistant"):
                        conn.execute("INSERT INTO conversation_messages(message_id,conversation_id,run_id,role,content,status,created_at,metadata) VALUES (?,?,?,?,?,'pending',?,?)",
                                     (request[f"{role}_message_id"], conversation_id, request["run_id"], role, content if role == "user" else "消息已登记，正在处理。", stamp,
                                      json.dumps({"request_id": request_id}, ensure_ascii=False)))
                    conn.execute("UPDATE conversations SET title=CASE WHEN last_message_at IS NULL THEN ? ELSE title END,updated_at=?,last_message_at=? WHERE conversation_id=?",
                                 (content[:40], stamp, stamp, conversation_id))
            dispatch = json.loads(request["dispatch"])
            try:
                if dispatch["operation"] == "resume":
                    result = self.workflows.get(dispatch["run_id"], principal)
                    if result["status"] == "awaiting_input":
                        result = self.workflows.resume(dispatch["run_id"], {"order_id": dispatch["order_id"]}, principal)
                    elif result["status"] == "failed":
                        result = self.workflows.recover(dispatch["run_id"], principal)
                else:
                    result = self.workflows.start(content, conversation["owner_user_id"], request_id, principal,
                                                  conversation_id=conversation_id, context=dispatch["context"])
                with self.store.connection() as conn:
                    conn.execute("UPDATE conversation_requests SET run_id=? WHERE actor_id=? AND request_id=?", (result["run_id"], principal.user_id, request_id))
                    conn.execute("UPDATE conversation_messages SET run_id=? WHERE message_id IN (?,?)", (result["run_id"], request["user_message_id"], request["assistant_message_id"]))
                self.store.sync_run(result)
                return self.envelope(request, result)
            except Exception:
                with self.store.connection() as conn:
                    # 不保存供应商原始异常，防止错误信息携带敏感内容。
                    conn.execute("UPDATE conversation_requests SET status='failed' WHERE actor_id=? AND request_id=?", (principal.user_id, request_id))
                    conn.execute("UPDATE conversation_messages SET status='failed',content=CASE WHEN role='assistant' THEN '处理暂未完成，请使用原请求重试。' ELSE content END WHERE message_id IN (?,?)", (request["user_message_id"], request["assistant_message_id"]))
                raise

    @staticmethod
    def envelope(request, result):
        return {**result, "conversation_id": request["conversation_id"], "message_id": request["user_message_id"],
                "assistant_message_id": request["assistant_message_id"]}
