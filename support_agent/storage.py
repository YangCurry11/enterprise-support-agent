# storage.py 负责把 Agent 的运行过程保存到 SQLite 数据库里。
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR


DB_PATH = DATA_DIR / "agent_logs.db"


def _json_dumps(data: Any) -> str:
    """
    把 Python 数据转成 JSON 字符串。
    ensure_ascii=False 表示中文正常保存。
    """
    return json.dumps(data, ensure_ascii=False, indent=2) 


def _json_loads(text: str, default: Any): # 把数据库里的 JSON 字符串重新转回 Python 数据。
    """
    把 JSON 字符串转回 Python 数据。
    如果解析失败，就返回默认值。
    """
    if not text:
        return default

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """
    创建 SQLite 数据库连接。
    如果数据库文件不存在，SQLite 会自动创建。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path) # 连接数据库
    conn.row_factory = sqlite3.Row # 让查询结果可以像字典一样读取
    return conn


def init_db() -> None: # 创建列表
    """
    初始化数据库表。
    如果表已经存在，不会重复创建。
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT,
                user_input TEXT,
                intent TEXT,
                order_id TEXT,
                need_human INTEGER,
                final_response TEXT,
                steps_json TEXT,
                tool_results_json TEXT,
                retrieved_docs_json TEXT,
                latency_ms INTEGER,
                created_at TEXT
            )
            """
        )
        conn.commit()


def save_agent_run(result: Dict[str, Any], latency_ms: int = 0) -> str:
    """
    保存一次 Agent 运行结果。

    result 就是 CustomerSupportAgent.run() 最后返回的完整字典。
    """
    init_db()

    run_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                run_id,
                user_id,
                user_input,
                intent,
                order_id,
                need_human,
                final_response,
                steps_json,
                tool_results_json,
                retrieved_docs_json,
                latency_ms,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result.get("user_id", ""),
                result.get("user_input", ""),
                result.get("intent", ""),
                result.get("order_id"),
                1 if result.get("need_human") else 0,
                result.get("final_response", ""),
                _json_dumps(result.get("steps", [])),
                _json_dumps(result.get("tool_results", {})),
                _json_dumps(result.get("retrieved_docs", [])),
                latency_ms,
                created_at,
            ),
        )
        conn.commit()

    return run_id


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """
    把数据库中的一行记录转成 Python 字典。
    """
    data = dict(row)

    data["need_human"] = bool(data.get("need_human"))
    data["steps"] = _json_loads(data.pop("steps_json", ""), [])
    data["tool_results"] = _json_loads(data.pop("tool_results_json", ""), {})
    data["retrieved_docs"] = _json_loads(data.pop("retrieved_docs_json", ""), [])

    return data


def list_agent_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """
    查询最近的 Agent 运行记录。
    """
    init_db()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agent_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_agent_run(run_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 run_id 查询某一次完整运行记录。
    """
    init_db()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_dict(row)


def clear_agent_runs() -> None:
    """
    清空所有 Agent 运行日志。
    调试时可以用，正式项目慎用。
    """
    init_db()

    with get_connection() as conn:
        conn.execute("DELETE FROM agent_runs")
        conn.commit()