from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR


# SQLite 业务数据库文件位置
DB_PATH = DATA_DIR / "business.db"


def _load_json(path: Path, default: Any) -> Any:
    """
    读取 JSON 文件。

    path：JSON 文件路径
    default：文件不存在时返回的默认值
    """
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """
    创建并返回 SQLite 数据库连接。

    SQLite 不需要单独启动服务。
    如果 business.db 不存在，会自动创建。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))

    # 让查询结果可以像字典一样使用
    conn.row_factory = sqlite3.Row

    return conn


def init_business_db() -> None:
    """
    初始化业务数据库。

    创建三张表：
    1. users：用户表
    2. orders：订单表
    3. tickets：工单表
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                level TEXT,
                phone_tail TEXT,
                city TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id TEXT,
                status TEXT,
                product TEXT,
                amount REAL,
                paid_at TEXT,
                logistics_company TEXT,
                tracking_number TEXT,
                estimated_delivery TEXT,
                received_days INTEGER,
                quality_issue INTEGER
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                user_id TEXT,
                order_id TEXT,
                issue_type TEXT,
                description TEXT,
                priority TEXT,
                status TEXT,
                created_at TEXT
            )
            """
        )

        conn.commit()


def _count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    """
    统计某张表中有多少条数据。
    """
    row = conn.execute(
        f"SELECT COUNT(*) AS count_value FROM {table_name}"
    ).fetchone()

    return int(row["count_value"])


def seed_business_db_from_json(overwrite: bool = False) -> None:
    """
    把原来的 JSON 数据导入 SQLite。

    overwrite=False：
        只有数据库表为空时才导入。

    overwrite=True：
        先清空数据库，再重新从 JSON 导入。
    """
    init_business_db()

    users_data = _load_json(DATA_DIR / "users.json", {})
    orders_data = _load_json(DATA_DIR / "orders.json", {})
    tickets_data = _load_json(DATA_DIR / "tickets.json", [])

    with get_connection() as conn:
        if overwrite:
            conn.execute("DELETE FROM tickets")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM users")

        # 导入用户
        if _count_rows(conn, "users") == 0 and isinstance(users_data, dict):
            for user_id, user in users_data.items():
                conn.execute(
                    """
                    INSERT INTO users (
                        user_id,
                        name,
                        level,
                        phone_tail,
                        city
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user.get("user_id", user_id).upper(),
                        user.get("name", ""),
                        user.get("level", ""),
                        user.get("phone_tail", ""),
                        user.get("city", ""),
                    ),
                )

        # 导入订单
        if _count_rows(conn, "orders") == 0 and isinstance(orders_data, dict):
            for order_id, order in orders_data.items():
                conn.execute(
                    """
                    INSERT INTO orders (
                        order_id,
                        user_id,
                        status,
                        product,
                        amount,
                        paid_at,
                        logistics_company,
                        tracking_number,
                        estimated_delivery,
                        received_days,
                        quality_issue
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.get("order_id", order_id).upper(),
                        order.get("user_id", ""),
                        order.get("status", ""),
                        order.get("product", ""),
                        order.get("amount", 0.0),
                        order.get("paid_at", ""),
                        order.get("logistics_company", ""),
                        order.get("tracking_number", ""),
                        order.get("estimated_delivery", ""),
                        order.get("received_days"),
                        1 if order.get("quality_issue") else 0,
                    ),
                )

        # 导入工单
        if _count_rows(conn, "tickets") == 0 and isinstance(tickets_data, list):
            for ticket in tickets_data:
                ticket_id = ticket.get("ticket_id")

                if not ticket_id:
                    continue

                conn.execute(
                    """
                    INSERT OR IGNORE INTO tickets (
                        ticket_id,
                        user_id,
                        order_id,
                        issue_type,
                        description,
                        priority,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        ticket.get("user_id", ""),
                        ticket.get("order_id"),
                        ticket.get("issue_type", ""),
                        ticket.get("description", ""),
                        ticket.get("priority", "normal"),
                        ticket.get("status", "open"),
                        ticket.get("created_at", ""),
                    ),
                )

        conn.commit()


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """
    根据订单号查询订单。
    """
    init_business_db()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = ?
            """,
            (order_id.upper(),),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    # 数据库中的 0/1 转回 Python 的 False/True
    result["quality_issue"] = bool(result.get("quality_issue"))

    return result


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    根据用户编号查询用户。
    """
    init_business_db()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id.upper(),),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def create_ticket(
    user_id: str,
    issue_type: str,
    description: str,
    order_id: Optional[str] = None,
    priority: str = "normal",
) -> Dict[str, Any]:
    """
    创建一条新工单，并写入 SQLite。
    """
    init_business_db()

    now = datetime.now()

    ticket_id = (
        f"TKT{now.strftime('%Y%m%d%H%M%S')}"
        f"{uuid.uuid4().hex[:4].upper()}"
    )

    record = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "order_id": order_id,
        "issue_type": issue_type,
        "description": description,
        "priority": priority,
        "status": "open",
        "created_at": now.isoformat(timespec="seconds"),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tickets (
                ticket_id,
                user_id,
                order_id,
                issue_type,
                description,
                priority,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["ticket_id"],
                record["user_id"],
                record["order_id"],
                record["issue_type"],
                record["description"],
                record["priority"],
                record["status"],
                record["created_at"],
            ),
        )

        conn.commit()

    return record


def list_tickets(limit: int = 100) -> List[Dict[str, Any]]:
    """
    查询最近的工单。
    """
    init_business_db()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tickets
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]