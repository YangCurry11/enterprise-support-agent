"""模型配置、可审计调用预算；不含供应商 Key 的日志/报告。"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import math
import os
import threading
from urllib.parse import urlsplit


class ModelConfigError(ValueError):
    code = "configuration_error"


class ModelServiceError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("模型调用未完成：" + code)


def _number(name, default, lower, upper, integer=False):
    try:
        value = int(os.getenv(name, str(default))) if integer else float(os.getenv(name, str(default)))
    except ValueError:
        raise ModelConfigError(f"{name} 必须为{'整数' if integer else '有限数值'}") from None
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ModelConfigError(f"{name} 必须位于 {lower}..{upper}")
    return value


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout: float
    temperature: float
    max_retries: int
    intent_enabled: bool

    @classmethod
    def read(cls):
        required = {name: os.getenv(name, "").strip() for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")}
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ModelConfigError("请明确配置 " + " / ".join(missing) + "；不会使用默认模型或默认供应商地址")
        try:
            url = urlsplit(required["LLM_BASE_URL"])
            valid = url.scheme in {"http", "https"} and url.hostname and not (url.username or url.password or url.query or url.fragment)
            _ = url.port
        except ValueError:
            valid = False
        if not valid:
            raise ModelConfigError("LLM_BASE_URL 必须是无用户名、密码、查询参数的 HTTP(S) 兼容接口地址")
        if url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ModelConfigError("非本机 LLM_BASE_URL 必须使用 HTTPS")
        if any(c.isspace() for c in required["LLM_MODEL"]) or len(required["LLM_MODEL"]) > 160:
            raise ModelConfigError("LLM_MODEL 必须填写实际模型 code，不能包含空白或超过160字符")
        enabled = os.getenv("LLM_INTENT_ENABLED", "false").lower()
        if enabled not in {"true", "false"}:
            raise ModelConfigError("LLM_INTENT_ENABLED 必须为 true 或 false")
        return cls(required["LLM_API_KEY"], required["LLM_BASE_URL"].rstrip("/"), required["LLM_MODEL"],
                   _number("LLM_TIMEOUT_SECONDS", 20, 0.1, 120), _number("LLM_TEMPERATURE", .2, 0, 2),
                   _number("LLM_MAX_RETRIES", 1, 0, 2, integer=True), enabled == "true")

    def public(self):
        # 不输出 URL（可含私有网关信息）或 Key，只输出模型 code 与主机。
        return {"model": self.model, "endpoint_host": urlsplit(self.base_url).hostname,
                "timeout_seconds": self.timeout, "max_retries": self.max_retries,
                "intent_enabled": self.intent_enabled, "key_configured": bool(self.api_key)}


def error_code(exc):
    """只检查异常类型/状态码；绝不序列化原始异常或供应商 body。"""
    if isinstance(exc, (ModelConfigError, ModelServiceError)):
        return exc.code
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if isinstance(exc, TimeoutError) or name in {"APITimeoutError", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout"}:
        return "timeout"
    if isinstance(exc, ConnectionError) or name in {"APIConnectionError", "ConnectError", "ReadError", "WriteError", "NetworkError"}:
        return "connection_error"
    if status in {401, 403}:
        return "authentication_error"
    if status == 429:
        return "rate_limit"
    if isinstance(status, int) and status >= 500:
        return "provider_error"
    if status in {400, 404, 422}:
        return "request_error"
    if name in {"ValidationError", "OutputParserException", "JSONDecodeError"}:
        return "invalid_response"
    return "provider_error"


@dataclass
class CallLedger:
    """一次 CLI 运行共享的物理请求硬预算；包含重试，不包含配置/预算拒绝。"""
    limit: int
    calls: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    simulated: bool = False

    def __post_init__(self):
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 500:
            raise ValueError("模型请求上限必须为 1..500 的整数")

    def reserve(self, operation, attempt, model):
        with self.lock:
            if len(self.calls) >= self.limit:
                raise ModelServiceError("budget_exhausted")
            row = {"call_id": len(self.calls) + 1, "operation": operation, "attempt": attempt,
                   "model": model, "success": False, "error_type": None, "latency_ms": 0,
                   "usage": None, "simulated": self.simulated}
            self.calls.append(row)
            return row

    def summary(self):
        with self.lock:
            rows = [dict(row) for row in self.calls]
        usages = [row["usage"] for row in rows if row["usage"] is not None]
        usage = {key: sum(item.get(key, 0) for item in usages) for key in ("input_tokens", "output_tokens", "total_tokens")} if usages else None
        return {"max_model_calls": self.limit, "actual_model_calls": len(rows),
                "call_count_definition": "client invoke request attempts, including retries; conservative upper bound, not provider billing confirmation",
                "successful_calls": sum(row["success"] for row in rows),
                "success_definition": "parsed output accepted by deterministic validation, not merely HTTP 2xx",
                "failed_calls": sum(not row["success"] for row in rows), "token_usage": usage,
                "usage_reported_calls": len(usages), "usage_complete": len(usages) == len(rows) if rows else False,
                "cost": None, "cost_note": "未配置经确认的计费规则，不估造费用；usage 只累加供应商实际返回部分",
                "calls": rows, "simulated": self.simulated}


_ledger = ContextVar("serviceflow_model_calls", default=None)


@contextmanager
def model_calls(ledger):
    token = _ledger.set(ledger)
    try:
        yield ledger
    finally:
        _ledger.reset(token)


def current_ledger():
    return _ledger.get()
