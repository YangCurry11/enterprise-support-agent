"""Server-side identity. Replace static credentials with OIDC before public rollout."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


bearer = HTTPBearer(auto_error=False)


def identities() -> dict[str, Principal]:
    raw = os.getenv("SUPPORT_AUTH_TOKENS", "")
    if not raw:
        if os.getenv("SUPPORT_ENV", "development") != "development":
            raise RuntimeError("SUPPORT_AUTH_TOKENS is required outside development")
        raw = '{"dev-customer-u1001":{"user_id":"U1001","role":"customer"},"dev-support-reviewer":{"user_id":"S1001","role":"support"}}'
    values = json.loads(raw)
    result = {}
    for token, value in values.items():
        if not token or value.get("role") not in {"customer", "support"} or not value.get("user_id"):
            raise RuntimeError("Invalid SUPPORT_AUTH_TOKENS configuration")
        result[token] = Principal(value["user_id"], value["role"])
    return result


def current_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials:
        for token, principal in identities().items():
            if secrets.compare_digest(credentials.credentials.encode(), token.encode()):
                return principal
    raise HTTPException(401, "访问凭证无效", headers={"WWW-Authenticate": "Bearer"})


def require_support(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role != "support":
        raise HTTPException(403, "此操作需要客服审核权限")
    return principal
