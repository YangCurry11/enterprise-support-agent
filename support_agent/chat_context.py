"""有界会话上下文：历史是参考，不是权限来源。"""
from dataclasses import dataclass
import os
import json
from fastapi import HTTPException
from .intent import ORDER_ID_PATTERN, classify_intent


def bounded_integer(name, default, lower, upper):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} 必须为整数") from None
    if not lower <= value <= upper:
        raise ValueError(f"{name} 必须位于 {lower}..{upper}")
    return value


@dataclass(frozen=True)
class ContextSettings:
    window: int
    max_chars: int
    enabled: bool

    @classmethod
    def read(cls):
        enabled = os.getenv("CHAT_CONTEXT_ENABLED", "true").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("CHAT_CONTEXT_ENABLED 必须为 true 或 false")
        return cls(bounded_integer("CHAT_HISTORY_WINDOW", 10, 1, 50),
                   bounded_integer("CHAT_MAX_CONTEXT_CHARS", 12000, 256, 24000), enabled == "true")


def resolve_context(text, conversation, messages, settings=None):
    settings = settings or ContextSettings.read()
    orders = {m.group().upper() for m in ORDER_ID_PATTERN.finditer(text)}
    if len(orders) > 1:
        raise HTTPException(422, "一次只处理一个订单，请明确本轮订单号")
    explicit = next(iter(orders), None)
    result = {"order_id": explicit, "order_source": "explicit" if explicit else "none", "history": []}
    if not settings.enabled:
        return result
    budget = settings.max_chars
    recent = []
    for item in reversed(messages[-settings.window:]):
        content = item["content"][-budget:]
        if not content:
            continue
        recent.append({"role": item["role"], "content": content})
        budget -= len(content)
        if budget <= 0:
            break
    result["history"] = list(reversed(recent))
    intent = classify_intent(text).intent
    referential = any(word in text for word in ("那", "它", "这单", "这个", "该订单", "申请售后"))
    business = intent in {"order_query", "refund_policy", "shipping_policy", "after_sales", "complaint"}
    if not explicit and conversation.get("verified_order_id") and (referential or business):
        result.update(order_id=conversation["verified_order_id"], order_source="verified_conversation")
        if intent == "unknown" and referential:
            result["intent_hint"] = "order_query"
    while len(json.dumps(result, ensure_ascii=False)) > settings.max_chars and result["history"]:
        item = result["history"][0]
        excess = len(json.dumps(result, ensure_ascii=False)) - settings.max_chars
        if len(item["content"]) <= excess:
            result["history"].pop(0)
        else:
            item["content"] = item["content"][excess:]
    return result
