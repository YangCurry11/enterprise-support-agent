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
from .model_runtime import error_code
from .order_facts import build_order_facts, receipt_summary


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
    conversation_id: Optional[str] = None
    conversation_context: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, name: str, detail: Dict[str, Any]): # 添加一个agent的执行情况
        self.steps.append(StepRecord(name=name, detail=detail))

    def to_dict(self): # 将AgentState转换为字典
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        return data


class IntentAgent: # 意图识别
    def run(self, state: AgentState) -> AgentState:
        result = classify_intent(state.user_input)
        from .llm_client import classify_with_llm
        result = classify_with_llm(state.user_input, result)
        state.intent = result.intent
        state.intent_confidence = result.confidence
        state.intent_reason = result.reason
        state.order_id = result.order_id or state.conversation_context.get("order_id")
        if result.intent == INTENT_UNKNOWN and state.conversation_context.get("intent_hint"):
            state.intent = state.conversation_context["intent_hint"]
            state.intent_reason = "服务端会话指代回退：" + state.intent_reason
            result.model_trace["context_override"] = True
        result.model_trace["final_prediction"] = state.intent
        state.add_step("IntentAgent", {
            "intent": state.intent,
            "confidence": state.intent_confidence,
            "reason": state.intent_reason,
            "order_id": state.order_id,
            "model_trace": result.model_trace,
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
        if not result.get("ok"):
            # 拒绝与工具错误使用确定性回复，不交给模型润色。
            state.final_response = "订单不存在或当前用户不可访问，未取得订单信息。"
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
        # 历史中确认过的编号不是授权凭据；每轮按业务客户范围重新读取。
        if state.order_id:
            order = self.tools.query_order(state.order_id)
            state.tool_results["query_order"] = order
            state.add_step("OrderContextCheck", {"tool": "query_order", "result": order})
            if not order.get("ok"):
                state.final_response = "订单不存在或当前用户不可访问，未查询该订单的政策适用情况。"
                return state
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

        if state.intent in [INTENT_REFUND, INTENT_SHIPPING, INTENT_AFTER_SALES]:
            order = state.tool_results.get("query_order", {})
            if order.get("ok"):
                data = order["data"]
                facts = build_order_facts(data)
                header = f"当前关联订单 {data['order_id']}，状态为【{data['status']}】。"
                if facts.receipt.conflicting_evidence:
                    header = f"当前关联订单 {data['order_id']}，签收记录冲突，无法确认状态字段【{data['status']}】所示签收情况。"
                state.final_response = header + "\n" + receipt_summary(facts) + "\n" + state.final_response
        state.add_step("ResponseAgent", {"final_response": state.final_response})
        return state

    def _summarize_by_intent(self, intent: str, query: str, docs: List[Dict[str, Any]]) -> str: # 根据意图和文档片段生成回复
        excerpts = "\n".join(f"[{index + 1}] {doc['text'][:500]}" for index, doc in enumerate(docs))
        return "检索到以下相关政策片段，是否适用还需要结合您的订单和具体情况确认：\n" + excerpts

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
            from .llm_client import generate_customer_reply, is_llm_enabled, reset_model_trace, last_model_trace

            reset_model_trace()

            if not is_llm_enabled():
                state.add_step("LLMResponseAgent", {
                    "mode": "disabled",
                    "reason": "未配置 LLM_API_KEY，使用模板回复"
                })
                return state

            if any(isinstance(result, dict) and result.get("ok") is False for result in state.tool_results.values()):
                state.add_step("LLMResponseAgent", {"mode": "blocked_tool_error", "model_used": False})
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
                conversation_context=state.conversation_context,
            )
            
            # 更新最终回复
            if llm_reply:
                state.final_response = llm_reply
                # 记录执行步骤
                state.add_step("LLMResponseAgent", {
                    "mode": "llm_generated",
                    "template_reply": template_reply,
                    "llm_reply": llm_reply,
                    "model_trace": last_model_trace(),
                })
            else:
                state.add_step("LLMResponseAgent", {"mode": "fallback_template", "error": "invalid_response", "model_used": False})

            return state

        except Exception as exc:
            # 5. 大模型失败时，保留原模板回复
            state.add_step("LLMResponseAgent", {
                "mode": "fallback_template",
                "error": error_code(exc),
                "model_trace": last_model_trace(),
                "template_reply": template_reply,
            })
            return state
        
class CustomerSupportAgent: # 客户支持代理：总控制器
    """多 Agent 编排器：意图识别 -> 工具/知识库 -> 工单 -> 回复。"""

    def __init__(self, tools: SupportTools | None = None): # 初始化agent
        self.tools = tools

    def run(self, user_input: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
        # CLI compatibility uses the same checkpointed workflow as HTTP requests.
        import uuid
        from .auth import Principal
        from .config import DATA_DIR
        from . import business_db
        from .runtime import WorkflowService
        business_db.seed_business_db_from_json(overwrite=False)
        kwargs = {"tools_factory": lambda _user, _run: self.tools} if self.tools else {}
        return WorkflowService(DATA_DIR, **kwargs).start(
            user_input, user_id, str(uuid.uuid4()), Principal(user_id, "customer"))
