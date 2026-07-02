from __future__ import annotations

from dataclasses import dataclass, field, asdict # dataclass数据类
from typing import Any, Dict, List, Optional # 类型注解 Dirt字典 List列表 Optional字符串或空

import time

from .config import DEFAULT_USER_ID # 默认用户ID
from .intent import (
    classify_intent,
    INTENT_ORDER, # 订单查询
    INTENT_REFUND, # 退款政策
    INTENT_SHIPPING, # 投诉
    INTENT_AFTER_SALES, 
    INTENT_COMPLAINT,
    INTENT_HUMAN,
    INTENT_CHITCHAT,
    INTENT_UNKNOWN,
)
from .tools import SupportTools  # 导入支持工具


@dataclass 
class StepRecord: # 记录每个agent的执行情况
    name: str
    detail: Dict[str, Any]


@dataclass
class AgentState: # 记录整个对话任务的状态
    user_input: str # 保存用户输入的问题
    user_id: str = DEFAULT_USER_ID # 保存用户ID
    intent: str = "" # 保存识别出来的意图
    intent_confidence: float = 0.0 # 保存意图识别的置信度 非模型算出
    intent_reason: str = "" # 保存意图识别的理由
    order_id: Optional[str] = None # 保存订单ID
    tool_results: Dict[str, Any] = field(default_factory=dict) # 保存工具的执行结果 
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list) # 保存RAG检索到的政策文档片段
    need_human: bool = False # 是否需要人工处理
    final_response: str = "" # 最终的回复
    steps: List[StepRecord] = field(default_factory=list) #保存每个agent的执行情况

    def add_step(self, name: str, detail: Dict[str, Any]): # 添加一个agent的执行情况
        self.steps.append(StepRecord(name=name, detail=detail))

    def to_dict(self): # 将AgentState转换为字典
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        return data


class IntentAgent: # 意图识别
    def run(self, state: AgentState) -> AgentState:
        result = classify_intent(state.user_input)
        state.intent = result.intent
        state.intent_confidence = result.confidence
        state.intent_reason = result.reason
        state.order_id = result.order_id
        state.add_step("IntentAgent", {
            "intent": state.intent,
            "confidence": state.intent_confidence,
            "reason": state.intent_reason,
            "order_id": state.order_id,
        })
        return state


class OrderAgent: # 订单查询
    def __init__(self, tools: SupportTools): # 初始化函数
        self.tools = tools

    def run(self, state: AgentState) -> AgentState:
        if not state.order_id:
            state.final_response = "请您提供订单号，例如 ORD1001，我才能帮您查询订单状态。"
            state.add_step("OrderAgent", {"action": "ask_order_id"})
            return state

        result = self.tools.query_order(state.order_id) # 调用工具查询订单
        state.tool_results["query_order"] = result
        state.add_step("OrderAgent", {
            "tool": "query_order", 
            "input": state.order_id, 
            "result": result
        })
        return state


class PolicyAgent: # 政策查询
    def __init__(self, tools: SupportTools):
        self.tools = tools

    def run(self, state: AgentState) -> AgentState:
        result = self.tools.search_policy(state.user_input, top_k=3) # 调用工具查询政策 top_k=3：最多返回3个相关片段
        state.tool_results["search_policy"] = result
        state.retrieved_docs = result.get("data", []) if result.get("ok") else [] # 如果查询成功，则保存检索到的政策文档片段
        state.add_step("PolicyAgent", {"tool": "search_policy", "query": state.user_input, "top_k": 3, "result": result})
        return state


class TicketAgent: # 工单创建
    def __init__(self, tools: SupportTools):
        self.tools = tools

    def run(self, state: AgentState, issue_type: str = "after_sales", priority: str = "normal") -> AgentState:
        result = self.tools.create_ticket(
            user_id=state.user_id,
            issue_type=issue_type,
            description=state.user_input,
            order_id=state.order_id,
            priority=priority, # 工单优先级 normal：普通，high：高，urgent：紧急
        )
        state.tool_results["create_ticket"] = result
        state.add_step("TicketAgent", {
            "tool": "create_ticket",
            "issue_type": issue_type,
            "priority": priority,
            "result": result,
        })
        return state


class ResponseAgent: # 回复生成
    def run(self, state: AgentState) -> AgentState:
        # 如果前面的节点已经需要追问，直接返回
        if state.final_response: # 如果已经有最终的回复，则直接返回 例如发现用户没有发订单号已经回复请提供订单号... 就不用生成了
            state.add_step("ResponseAgent", {"mode": "pass_through"})
            return state

        if state.intent == INTENT_ORDER:
            order_result = state.tool_results.get("query_order", {})
            if not order_result.get("ok"):
                state.final_response = f"抱歉，我没有查询到该订单信息。{order_result.get('error', '')}"
            else:
                order = order_result["data"]
                if order.get("status") == "已发货":
                    state.final_response = (
                        f"我帮您查询到订单 {order['order_id']} 当前状态为【{order['status']}】。"
                        f"商品是 {order['product']}，物流公司为 {order.get('logistics_company') or '暂无'}，"
                        f"物流单号为 {order.get('tracking_number') or '暂无'}，预计送达时间：{order.get('estimated_delivery') or '暂无'}。"
                    )
                elif order.get("status") == "待发货":
                    state.final_response = (
                        f"订单 {order['order_id']} 当前状态为【待发货】，商品是 {order['product']}。"
                        f"系统显示：{order.get('estimated_delivery', '预计尽快发货')}。如果超过承诺时间未发货，我可以为您创建物流/发货异常工单。"
                    )
                else:
                    state.final_response = (
                        f"订单 {order['order_id']} 当前状态为【{order.get('status')}】，商品是 {order.get('product')}。"
                        f"补充信息：{order.get('estimated_delivery', '')}。"
                    )
        elif state.intent in [INTENT_REFUND, INTENT_SHIPPING, INTENT_AFTER_SALES, INTENT_UNKNOWN]:
            docs = state.retrieved_docs
            if docs: # 如果有检索到政策文档片段
                evidence = "\n".join([f"- 来源：{d['source']}；片段：{d['text'][:120]}..." for d in docs]) # 截取片段前120个字符
                sources = "、".join(sorted({d["source"] for d in docs})) # 去重排序
                state.final_response = (
                    "根据我检索到的企业政策，给您的建议如下：\n"
                    f"{self._summarize_by_intent(state.intent, state.user_input, docs)}\n\n"
                    f"依据来源：{sources}\n"
                    "如果您的情况涉及质量问题、投诉或金额争议，我建议创建售后工单并转人工进一步处理。"
                )
                state.tool_results["evidence_preview"] = evidence
            else:
                state.final_response = "我没有在知识库中检索到足够明确的政策依据，建议转人工客服确认。"
                state.need_human = True
        elif state.intent == INTENT_COMPLAINT: # 投诉回复
            ticket = state.tool_results.get("create_ticket", {})
            if ticket.get("ok"):
                state.final_response = (
                    f"非常抱歉给您带来不好的体验。我已为您创建高优先级投诉工单，"
                    f"工单号为 {ticket['data']['ticket_id']}，会由人工客服继续跟进。"
                )
            else:
                state.final_response = "非常抱歉，我尝试创建投诉工单失败了，请稍后重试或直接联系人工客服。"
        elif state.intent == INTENT_HUMAN:
            ticket = state.tool_results.get("create_ticket", {})
            if ticket.get("ok"):
                state.final_response = f"已为您转人工处理，并创建工单 {ticket['data']['ticket_id']}。人工客服会继续跟进。"
            else:
                state.final_response = "我理解您希望联系人工客服，但当前创建工单失败，请稍后再试。"
        elif state.intent == INTENT_CHITCHAT:
            state.final_response = "您好，我是智能客服助手。您可以告诉我订单号、退款问题、物流问题或售后问题。"
        else:
            state.final_response = "我暂时无法准确判断您的问题类型，请补充订单号、退款原因或售后问题描述。"

        state.add_step("ResponseAgent", {"final_response": state.final_response})
        return state

    def _summarize_by_intent(self, intent: str, query: str, docs: List[Dict[str, Any]]) -> str: # 根据意图和文档片段生成回复
        joined = "\n".join(d["text"] for d in docs) 
        if intent == INTENT_REFUND or "退" in query:
            if "超过7天" in joined or "签收超过7天" in joined:
                return "非质量问题商品通常仅支持签收后7天内无理由退货；如果超过7天但存在质量问题，可以申请售后检测，检测通过后再按规则处理退换或维修。"
            return "退货/退款需要结合签收时间、商品状态和是否存在质量问题判断。请您提供签收时间和商品问题，我可以继续判断。"
        if intent == INTENT_SHIPPING or any(w in query for w in ["物流", "发货", "快递"]):
            return "现货商品通常付款后24小时内发货；如果物流超过预计时间未更新，建议创建物流异常工单并转人工跟进。"
        if intent == INTENT_AFTER_SALES or any(w in query for w in ["坏", "维修", "少件"]):
            return "商品损坏、无法使用、少件、错发等情况应创建售后工单，并附上照片、视频或问题描述，便于人工客服审核处理。"
        return "请结合退款、物流、售后政策处理；若存在争议、投诉或复杂情况，应转人工。"

# LLM 回复 Agent
class LLMResponseAgent(ResponseAgent): # LLMResponseAgent 继承 ResponseAgent
    """
    LLM 回复 Agent。

    它先调用原来的 ResponseAgent 生成模板回复，
    再调用大模型把模板回复润色成更自然的客服话术。
    如果大模型失败，就保留原模板回复。
    """

    def run(self, state: AgentState) -> AgentState:
        # 1. 先用原来的固定模板生成一个兜底回复
        state = super().run(state) # 调用父类 ResponseAgent 的 run 方法
        template_reply = state.final_response

        try:
            from .llm_client import generate_customer_reply, is_llm_enabled

            if not is_llm_enabled():
                state.add_step("LLMResponseAgent", {
                    "mode": "disabled",
                    "reason": "未配置 LLM_API_KEY，使用模板回复"
                })
                return state

            # 2. 从 tool_results 里取订单信息
            order_info = None
            order_result = state.tool_results.get("query_order", {})
            if isinstance(order_result, dict) and order_result.get("ok"):
                order_info = order_result.get("data")

            # 3. 从 tool_results 里取工单信息
            ticket_info = None
            ticket_result = state.tool_results.get("create_ticket", {})
            if isinstance(ticket_result, dict) and ticket_result.get("ok"):
                ticket_info = ticket_result.get("data")

            # 4. 调用大模型生成回复
            llm_reply = generate_customer_reply(
                user_question=state.user_input,
                intent=state.intent,
                order_info=order_info,
                policy_docs=state.retrieved_docs,
                ticket_info=ticket_info,
                need_human=state.need_human,
                template_reply=template_reply,
            )
            
            # 更新最终回复
            if llm_reply:
                state.final_response = llm_reply
                # 记录执行步骤
                state.add_step("LLMResponseAgent", {
                    "mode": "llm_generated",
                    "template_reply": template_reply,
                    "llm_reply": llm_reply,
                })

            return state

        except Exception as exc:
            # 5. 大模型失败时，保留原模板回复
            state.add_step("LLMResponseAgent", {
                "mode": "fallback_template",
                "error": str(exc),
                "template_reply": template_reply,
            })
            return state
        
class CustomerSupportAgent: # 客户支持代理：总控制器
    """多 Agent 编排器：意图识别 -> 工具/知识库 -> 工单 -> 回复。"""

    def __init__(self, tools: SupportTools | None = None): # 初始化agent
        self.tools = tools or SupportTools() # 如果没有传入工具，则使用默认工具
        self.intent_agent = IntentAgent()
        self.order_agent = OrderAgent(self.tools)
        self.policy_agent = PolicyAgent(self.tools)
        self.ticket_agent = TicketAgent(self.tools)
        self.response_agent = LLMResponseAgent()

    def run(self, user_input: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
        start_time = time.perf_counter() # 记录开始时间

        state = AgentState(user_input=user_input, user_id=user_id)

        state = self.intent_agent.run(state)

        if state.intent == INTENT_ORDER:
            state = self.order_agent.run(state)

        elif state.intent in [INTENT_REFUND, INTENT_SHIPPING, INTENT_AFTER_SALES, INTENT_UNKNOWN]:
            state = self.policy_agent.run(state)

            if state.intent == INTENT_AFTER_SALES:
                state = self.ticket_agent.run(
                    state,
                    issue_type="after_sales",
                    priority="normal",
                )

        elif state.intent == INTENT_COMPLAINT:
            state.need_human = True
            state = self.ticket_agent.run(
                state,
                issue_type="complaint",
                priority="high",
            )

        elif state.intent == INTENT_HUMAN:
            state.need_human = True
            state = self.ticket_agent.run(
                state,
                issue_type="human_escalation",
                priority="high",
            )

        state = self.response_agent.run(state)

        result = state.to_dict()

        latency_ms = int((time.perf_counter() - start_time) * 1000) # 计算耗时

        try:
            # 保存日志
            from .storage import save_agent_run

            run_id = save_agent_run(result, latency_ms=latency_ms)
            result["run_id"] = run_id
            result["latency_ms"] = latency_ms

        except Exception as exc:
            result["storage_error"] = str(exc)
            result["latency_ms"] = latency_ms

        return result
