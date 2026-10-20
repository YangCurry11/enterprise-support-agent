"""Explicit, checkpointed customer-support workflow; mutations follow review."""
from __future__ import annotations

import time
import sqlite3
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt, RetryPolicy
from .agents import AgentState, StepRecord, IntentAgent, OrderAgent, PolicyAgent, TicketAgent, LLMResponseAgent, ResponseAgent
from .intent import extract_order_id


class WorkflowState(TypedDict, total=False):
    data: dict[str, Any]
    run_id: str
    review: dict[str, Any]


def unpack(raw: dict) -> AgentState:
    values = dict(raw)
    values["steps"] = [StepRecord(**step) for step in values.get("steps", [])]
    return AgentState(**values)


def build_graph(tools, checkpointer):
    def execute(agent, raw):
        state = unpack(raw["data"])
        started = time.perf_counter()
        state = agent.run(state)
        if state.steps:
            state.steps[-1].detail["duration_ms"] = round((time.perf_counter() - started) * 1000)
        return {"data": state.to_dict()}

    def identify(raw):
        result = execute(IntentAgent(), raw)
        if result["data"]["intent"] in {"complaint", "human_escalation"}:
            result["data"]["need_human"] = True
        return result

    def route(raw):
        intent = raw["data"]["intent"]
        if intent == "order_query":
            return "clarify"
        if intent in {"refund_policy", "shipping_policy", "after_sales", "unknown"}:
            return "policy"
        if intent in {"complaint", "human_escalation"}:
            return "review"
        return "response"

    def clarify(raw):
        state = unpack(raw["data"])
        if not state.order_id:
            answer = interrupt({"kind": "order_id", "message": "请提供订单号，例如 ORD1001。"})
            state.order_id = extract_order_id(answer["order_id"])
            if not state.order_id:
                raise ValueError("Invalid order ID")
            state.add_step("ClarificationAgent", {"order_id": state.order_id})
        return {"data": state.to_dict()}

    def review(raw):
        state = unpack(raw["data"])
        # Never expose another customer's order to the reviewer through this workflow.
        if state.order_id and not tools.query_order(state.order_id)["ok"]:
            state.final_response = "订单不存在或当前用户不可访问，未创建工单。"
            state.add_step("ReviewAgent", {"action": "blocked_order_access"})
            return {"data": state.to_dict(), "review": {"approved": False}}
        answer = interrupt({"kind": "approval", "message": "该请求需要客服审核后创建工单。",
                            "intent": state.intent, "order_id": state.order_id})
        state.add_step("ReviewAgent", answer)
        if not answer["approved"]:
            state.final_response = "客服审核未通过，本次未创建工单。请补充信息或联系人工客服。"
        return {"data": state.to_dict(), "review": answer}

    def ticket(raw):
        state = unpack(raw["data"])
        issue_type = state.intent
        priority = "high" if issue_type in {"complaint", "human_escalation"} else "normal"
        state = TicketAgent(tools).run(state, issue_type=issue_type, priority=priority)
        if not state.tool_results["create_ticket"].get("ok"):
            state.final_response = "工单创建未成功，未承诺处理结果。请联系人工客服。"
            state.need_human = True
        elif issue_type == "after_sales":
            ticket_id = state.tool_results["create_ticket"]["data"]["ticket_id"]
            state.final_response = f"已创建售后工单 {ticket_id}，由客服跟进。工单创建不代表退款或赔偿已获批准。"
        return {"data": state.to_dict()}

    def response(raw):
        # Preserve deterministic refusals and clarification replies.
        agent = ResponseAgent() if raw["data"]["final_response"] else LLMResponseAgent()
        return execute(agent, raw)

    graph = StateGraph(WorkflowState)
    graph.add_node("intent", identify)
    graph.add_node("clarify", clarify)
    read_retry = RetryPolicy(initial_interval=0.05, max_attempts=3, retry_on=(TimeoutError, ConnectionError, sqlite3.OperationalError))
    graph.add_node("order", lambda raw: execute(OrderAgent(tools), raw), retry_policy=read_retry)
    graph.add_node("policy", lambda raw: execute(PolicyAgent(tools), raw), retry_policy=read_retry)
    graph.add_node("review", review)
    graph.add_node("ticket", ticket)
    graph.add_node("response", response)
    graph.add_edge(START, "intent")
    graph.add_conditional_edges("intent", route, {name: name for name in ["clarify", "policy", "review", "response"]})
    graph.add_edge("clarify", "order")
    graph.add_edge("order", "response")
    graph.add_conditional_edges("policy", lambda raw: "review" if raw["data"]["intent"] == "after_sales" else "response",
                                {"review": "review", "response": "response"})
    graph.add_conditional_edges("review", lambda raw: "ticket" if raw["review"]["approved"] else "response",
                                {"ticket": "ticket", "response": "response"})
    graph.add_edge("ticket", "response")
    graph.add_edge("response", END)
    return graph.compile(checkpointer=checkpointer)
