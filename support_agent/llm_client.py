# 大模型客户端
from __future__ import annotations

import os
import json
from functools import lru_cache # 缓存工具
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


def _to_json(data: Any) -> str:
    """
    把 Python 数据转成好看的 JSON 字符串。
    ensure_ascii=False 表示中文正常显示。
    """
    return json.dumps(data, ensure_ascii=False, indent=2)


def is_llm_enabled() -> bool:
    """
    判断是否配置了大模型 API Key。
    如果没有配置，就不调用大模型。
    """
    load_dotenv()
    return bool(os.getenv("LLM_API_KEY"))


@lru_cache(maxsize=1) 
def get_llm() -> ChatOpenAI:
    """
    创建并缓存大模型对象。

    需要 .env 中配置：
    LLM_API_KEY=你的key
    LLM_BASE_URL=https://api.deepseek.com
    LLM_MODEL=deepseek-v4-flash
    """
    load_dotenv()

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_name = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2")) # 默认0.2

    if not api_key:
        raise ValueError("未配置 LLM_API_KEY，无法调用大模型。")

    kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": temperature,
    }

    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)


def generate_customer_reply(
    user_question: str,
    intent: str, # 识别意图
    order_info: Optional[Dict[str, Any]] = None,
    policy_docs: Optional[List[Dict[str, Any]]] = None,
    ticket_info: Optional[Dict[str, Any]] = None,
    need_human: bool = False,
    template_reply: str = "",
) -> str:
    """
    根据用户问题、订单信息、政策依据、工单信息，调用大模型生成客服回复。

    注意：
    这里的大模型只负责“生成回复”，不负责查订单、不负责查政策、不负责建工单。
    """

    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
你是一个企业电商客服助手。

你需要根据提供的业务数据，生成最终客服回复。

严格要求：
1. 语气礼貌、自然、简洁。
2. 只能依据提供的数据回答，不要编造订单状态、物流单号、退款承诺。
3. 如果订单信息为空，不要假装查到了订单。
4. 如果政策依据为空，不要编造企业政策。
5. 如果涉及投诉、赔偿、支付异常、隐私问题，要建议转人工客服。
6. 如果已有工单信息，要明确告诉用户工单号和后续处理方式。
7. 不要使用 Markdown 格式，不要加粗，不要输出标题，直接输出纯文本客服回复。
"""
        ),
        (
            "human",
            """
用户问题：
{user_question}

识别出的意图：
{intent}

是否需要人工：
{need_human}

订单信息：
{order_info}

政策依据：
{policy_docs}

工单信息：
{ticket_info}

原模板回复：
{template_reply}

请基于以上信息，生成最终客服回复：
"""
        )
    ])

    chain = prompt | llm

    result = chain.invoke({
        "user_question": user_question,
        "intent": intent,
        "need_human": str(need_human),
        "order_info": _to_json(order_info),
        "policy_docs": _to_json(policy_docs or []),
        "ticket_info": _to_json(ticket_info),
        "template_reply": template_reply,
    })

    return result.content.strip()