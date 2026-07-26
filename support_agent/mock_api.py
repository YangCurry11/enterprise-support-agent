# 模拟企业内部订单、用户、工单和政策接口，供 Agent 工具调用。 （模拟后端系统
from __future__ import annotations

from datetime import datetime # 获取当前时间，用来创建工单号
from pathlib import Path
from typing import Optional # 表示某个字段可以有，也可以没有。
import json

from fastapi import FastAPI, HTTPException 
from pydantic import BaseModel, Field  # 定义请求参数和响应数据的模型
 
from .config import DATA_DIR, POLICY_DIR

from .business_db import (
    init_business_db,
    seed_business_db_from_json,
    get_order as db_get_order,
    get_user as db_get_user,
    create_ticket as db_create_ticket,
    list_tickets as db_list_tickets,
)

# 创建 FastAPI 应用
app = FastAPI(
    title="Mock Enterprise Support API",
    description="模拟企业内部订单、用户、工单和政策接口，供 Agent 工具调用。",
    version="0.1.0",
)

init_business_db()
seed_business_db_from_json(overwrite=False)

# 读取json文件
def _load_json(path: Path):
    if not path.exists(): # path.exists() 判断文件是否存在
        return {} if path.suffix == ".json" else None # path.suffix 是文件后缀名
    # python读取json文件的标准写法
    with path.open("r", encoding="utf-8") as f:
        return json.load(f) 

# 写json文件
def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True) # mkdir 确保文件存在，不存在就创建
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2) # json.dump 将python字典或列表保存成json文件
    # ensure_ascii=False 表示中文正常保存，不变成乱码  indent=2 格式化缩进

class TicketCreate(BaseModel): # TicketCreate是一个接口请求数据模型
    user_id: str = Field(default="U1001", description="用户编号") #不传默认是U1001
    issue_type: str = Field(..., description="问题类型，如 refund/order/complaint/shipping") #... 表示这个字段必填
    description: str = Field(..., description="问题描述")
    order_id: Optional[str] = Field(default=None, description="订单号，可选")
    priority: str = Field(default="normal", description="优先级：low/normal/high")

# 健康检查接口 ：确认后端 API 是否正常启动
@app.get("/")
def health_check():
    return {"status": "ok", "service": "mock enterprise support api"}


@app.get("/orders/{order_id}")  #查询订单接口，直接查找SQLite数据库中的orders表
def get_order(order_id: str): 
    order = db_get_order(order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"订单不存在：{order_id}"
        )

    return order


@app.get("/users/{user_id}") # 查询用户接口，直接查找SQLite数据库中的users表
def get_user(user_id: str):
    user = db_get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"用户不存在：{user_id}"
        )

    return user


@app.post("/tickets") # 创建工单接口，直接插入SQLite数据库中的tickets表，创建工单逻辑在business_db.py中
def create_ticket(ticket: TicketCreate):
    return db_create_ticket(
        user_id=ticket.user_id,
        issue_type=ticket.issue_type,
        description=ticket.description,
        order_id=ticket.order_id,
        priority=ticket.priority,
    )


@app.get("/tickets") # 工单列表接口，直接查找SQLite数据库中的tickets表
def list_tickets():
    return db_list_tickets()


@app.get("/policies") # 政策列表接口
def list_policies():
    files = sorted(POLICY_DIR.glob("*.md")) # 找所有.md文件
    return [{"name": f.stem, "filename": f.name} for f in files] # 返回文件信息


@app.get("/policies/{policy_name}") # 读取政策接口
def get_policy(policy_name: str):
    candidate = POLICY_DIR / f"{policy_name}.md"
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"政策文档不存在：{policy_name}")
    return {"name": policy_name, "content": candidate.read_text(encoding="utf-8")}
