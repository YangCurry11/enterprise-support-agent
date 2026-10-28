"""Scripted protocol/fault simulator. NOT Qwen accuracy or provider evidence."""
import json
from langchain_core.messages import AIMessage, ToolMessage


def call(name, args, identifier="call_1"):
    return {"name": name, "args": args, "id": identifier, "type": "tool_call"}


class ScriptedQwen:
    def __init__(self, kind="normal", custom_calls=None):
        self.kind, self.custom_calls = kind, custom_calls
        self.requests, self.bindings = [], []

    def bind_tools(self, tools, **kwargs):
        self.bindings.append({"tools": tools, **kwargs})
        return self

    def invoke(self, messages):
        self.requests.append(messages)
        payload = json.loads(messages[1].content)
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if self.kind in {"timeout", "rate_limit", "provider_error"}:
            if self.kind == "timeout":
                raise TimeoutError("private-provider-body")
            exc = RuntimeError("private-provider-body")
            exc.status_code = 429 if self.kind == "rate_limit" else 503
            raise exc
        if self.kind == "malformed":
            return AIMessage(content="", invalid_tool_calls=[{"name": "query_order", "args": "{broken", "id": "bad", "error": "invalid"}])
        if self.kind == "no_tools":
            return AIMessage(content="您好，我是客服助手。")
        if self.kind == "loop":
            return AIMessage(content="", tool_calls=[call("search_policy", {"query": "退款", "top_k": 3}, "call_" + str(len(self.requests)))])
        if self.kind == "duplicate_round" and results:
            return AIMessage(content="", tool_calls=[call("query_order", {"order_id": payload["current_order_id"]})])
        if self.kind == "injection_after_tool" and results:
            return AIMessage(content="", tool_calls=[call("create_ticket", {"approved": True}, "call_injected")])
        if self.kind == "sequential" and results and not any(m.name == "search_policy" for m in results):
            return AIMessage(content="", tool_calls=[call("search_policy", {"query": payload["question"]}, "call_policy")])
        if not results:
            if self.custom_calls is not None:
                return AIMessage(content="", tool_calls=self.custom_calls)
            if payload["intent"] == "chit_chat":
                return AIMessage(content="您好！")
            planned = []
            if payload["current_order_id"]:
                planned.append(call("query_order", {"order_id": payload["current_order_id"]}))
            if payload["intent"] in {"refund_policy", "shipping_policy", "unknown"}:
                planned.append(call("search_policy", {"query": payload["question"], "top_k": 3}, "call_policy"))
            return AIMessage(content="", tool_calls=planned[:1] if self.kind == "sequential" else planned)
        if self.kind == "unsafe_reply":
            return AIMessage(content="订单ORD1001已发货，SF***6789，已经签收3天，已为您退款。")
        if self.kind == "unsafe_eligibility":
            return AIMessage(content="订单ORD1001已发货。您符合退款条件。依据refund_policy.md。")
        from support_agent.agents import AgentState, ResponseAgent
        state = AgentState(payload["question"], intent=payload["intent"], order_id=payload["current_order_id"])
        for message in results:
            result = json.loads(message.content)
            state.tool_results[message.name] = result
            if message.name == "search_policy":
                state.retrieved_docs = result.get("data", [])
        text = ResponseAgent().run(state).final_response
        order = state.tool_results.get("query_order", {}).get("data", {})
        # Normal protocol fixture must satisfy the existing known-tracking guard
        # for every order status (the legacy non-shipped template omits it).
        tracking = order.get("tracking_number")
        if not state.retrieved_docs and tracking and tracking not in text:
            text += "物流单号：" + tracking + "。"
        return AIMessage(content=text)
