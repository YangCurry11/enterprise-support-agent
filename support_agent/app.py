"""Authenticated HTTP boundary for support workflows and sandbox business data."""
from __future__ import annotations
from contextlib import asynccontextmanager
import logging
import re
import uuid
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from .auth import Principal, current_principal, require_support, identities
from .config import CORS_ORIGINS, DATA_DIR, POLICY_DIR
from . import business_db
from .runtime import WorkflowService


@asynccontextmanager
async def lifespan(app):
    identities()
    business_db.init_business_db()
    business_db.seed_business_db_from_json(overwrite=False)
    app.state.workflows = WorkflowService(DATA_DIR)
    yield


app = FastAPI(title="Enterprise Support Workflow API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(CORS_ORIGINS), allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"],
                   expose_headers=["X-Request-ID"])


@app.middleware("http")
async def request_id(request, call_next):
    trace_id = str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception("Unhandled request error request_id=%s", trace_id)
        from fastapi.responses import JSONResponse
        response = JSONResponse({"detail": "服务暂时不可用", "request_id": trace_id}, status_code=500)
    response.headers["X-Request-ID"] = trace_id
    return response


class StrictRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AgentRunRequest(StrictRequest):
    user_input: str = Field(min_length=1, max_length=1000)
    user_id: str | None = Field(default=None, min_length=1, max_length=50)
    request_id: uuid.UUID


class ResumeRequest(StrictRequest):
    order_id: str = Field(pattern=r"^ORD\d{4,}$", max_length=40)


class ReviewRequest(StrictRequest):
    approved: bool = Field(strict=True)
    note: str = Field(default="", max_length=500)


def service(request: Request):
    return request.app.state.workflows


@app.get("/")
def health_check():
    return {"status": "ok", "service": "enterprise support workflow", "version": "0.2.0"}


@app.get("/me")
def me(principal: Principal = Depends(current_principal)):
    return {"user_id": principal.user_id, "role": principal.role}


@app.post("/agent/run")
def run_agent(payload: AgentRunRequest, principal: Principal = Depends(current_principal), workflows=Depends(service)):
    user_id = payload.user_id or principal.user_id
    if principal.role != "support" and user_id != principal.user_id:
        raise HTTPException(403, "不能代其他用户发起请求")
    if not business_db.get_user(user_id):
        raise HTTPException(404, "用户不存在")
    return workflows.start(payload.user_input, user_id, str(payload.request_id), principal)


@app.get("/agent/runs")
def agent_runs(limit: int = Query(10, ge=1, le=50), principal: Principal = Depends(current_principal), workflows=Depends(service)):
    return {"runs": workflows.history(principal, limit)}


@app.get("/agent/runs/{run_id}")
def get_run(run_id: str, principal: Principal = Depends(current_principal), workflows=Depends(service)):
    return workflows.get(run_id, principal)


@app.get("/agent/reviews")
def review_queue(limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0), principal: Principal = Depends(require_support), workflows=Depends(service)):
    return {"runs": workflows.reviews(principal, limit, offset)}


@app.post("/agent/runs/{run_id}/resume")
def resume_run(run_id: str, payload: ResumeRequest, principal: Principal = Depends(current_principal), workflows=Depends(service)):
    return workflows.resume(run_id, payload.model_dump(), principal)


@app.post("/agent/runs/{run_id}/review")
def review_run(run_id: str, payload: ReviewRequest, principal: Principal = Depends(require_support), workflows=Depends(service)):
    return workflows.resume(run_id, payload.model_dump(), principal, review=True)


@app.post("/agent/runs/{run_id}/retry")
def retry_run(run_id: str, principal: Principal = Depends(current_principal), workflows=Depends(service)):
    return workflows.recover(run_id, principal)


@app.get("/agent/runs/{run_id}/audit")
def audit_run(run_id: str, principal: Principal = Depends(require_support), workflows=Depends(service)):
    return {"events": workflows.events(run_id, principal)}


@app.get("/orders/{order_id}")
def get_order(order_id: str, principal: Principal = Depends(current_principal)):
    order = business_db.get_order(order_id)
    if not order or (principal.role != "support" and order["user_id"] != principal.user_id):
        raise HTTPException(404, "订单不存在或不可访问")
    return order


@app.get("/users/{user_id}")
def get_user(user_id: str, principal: Principal = Depends(current_principal)):
    if principal.role != "support" and user_id != principal.user_id:
        raise HTTPException(404, "用户不存在或不可访问")
    user = business_db.get_user(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


@app.get("/tickets")
def list_tickets(principal: Principal = Depends(current_principal)):
    return business_db.list_tickets(user_id=principal.user_id if principal.role == "customer" else None)


@app.get("/policies")
def list_policies(principal: Principal = Depends(current_principal)):
    return [{"name": file.stem, "filename": file.name} for file in sorted(POLICY_DIR.glob("*.md"))]


@app.get("/policies/{policy_name}")
def get_policy(policy_name: str, principal: Principal = Depends(current_principal)):
    if not re.fullmatch(r"[\w-]+", policy_name):
        raise HTTPException(404, "政策不存在")
    candidate = POLICY_DIR / f"{policy_name}.md"
    if not candidate.is_file():
        raise HTTPException(404, "政策不存在")
    return {"name": policy_name, "content": candidate.read_text(encoding="utf-8")}
