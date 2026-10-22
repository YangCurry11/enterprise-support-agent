"""会话 API 的类型契约；未知入参拒绝，复用原运行结果的字段。"""
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="新会话", min_length=1, max_length=80)
    owner_user_id: str | None = Field(default=None, min_length=1, max_length=50)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=1000)
    request_id: UUID

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空白")
        return value  # 校验但不改写 API 收到的原始消息。


class ConversationView(BaseModel):
    conversation_id: str
    owner_user_id: str
    title: str
    created_at: str
    updated_at: str
    last_message_at: str | None
    status: str
    verified_order_id: str | None


class ConversationList(BaseModel):
    conversations: list[ConversationView]
    limit: int
    offset: int


class MessageView(BaseModel):
    sequence: int
    message_id: str
    conversation_id: str
    run_id: str | None
    role: Literal["user", "assistant", "system"]
    content: str
    status: str
    created_at: str
    metadata: dict[str, Any]


class MessageList(BaseModel):
    messages: list[MessageView]
    next_before: int | None


class MessageResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    conversation_id: str
    message_id: str
    assistant_message_id: str
    run_id: str
    final_response: str
    status: str
    pending: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    latency_ms: int
