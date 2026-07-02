# 测试大模型能不能正常工作
from __future__ import annotations

import os # 读取环境变量
import json
from dotenv import load_dotenv # 读取.env文件

from langchain_openai import ChatOpenAI # 调用openai的类
from langchain_core.prompts import ChatPromptTemplate # 创建prompt模板的类


def build_llm():
    """
    创建大模型对象。

    需要在 .env 里配置：
    LLM_API_KEY=你的API Key
    LLM_BASE_URL=https://api.deepseek.com
    LLM_MODEL=deepseek-v4-flash
    """

    load_dotenv() # 读取项目根目录的.env文件

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_name = os.getenv("LLM_MODEL", "deepseek-v4-flash")

    if not api_key:
        raise ValueError("没有读取到 LLM_API_KEY，请先在 .env 文件中配置。")

    kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": 0.2, # 控制模型回答稳定性，越低越稳定
    }

    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs) 
    # **kwargs 表示将字典中的键值对作为参数传递给函数 是python的展开写法 
    # 相当于 ： ChatOpenAI(
    #     model=model_name,
    #     api_key=api_key,
    #     temperature=0.2,
    #     base_url=base_url
    # )

def main():
    llm = build_llm()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
你是一个企业电商客服助手。

请根据用户问题和已知业务数据生成客服回复。

要求：
1. 语气礼貌、自然、简洁。
2. 只能依据提供的数据回答，不要编造订单状态、物流单号、退款承诺。
3. 如果信息不足，要说明需要进一步确认。
4. 如果涉及投诉、赔偿、支付异常、隐私问题，建议转人工客服。
5. 如果使用了政策依据，要说明依据来源。
"""
        ),
        (
            "human",
            """
用户问题：
{user_question}

订单信息：
{order_info}

政策依据：
{policy_docs}

工单信息：
{ticket_info}

请生成最终客服回复：
"""
        )
    ])

    chain = prompt | llm # 将prompt和llm组合起来

    user_question = "我的订单 ORD1001 到哪了？"

    order_info = {
        "order_id": "ORD1001",
        "status": "已发货",
        "product": "无线蓝牙耳机",
        "logistics_company": "顺丰",
        "tracking_number": "SF123456789",
        "estimated_delivery": "2天内"
    }

    policy_docs = []

    ticket_info = None

    # 调用大模型
    result = chain.invoke({
        "user_question": user_question,
        "order_info": json.dumps(order_info, ensure_ascii=False, indent=2),
        "policy_docs": json.dumps(policy_docs, ensure_ascii=False, indent=2),
        "ticket_info": json.dumps(ticket_info, ensure_ascii=False, indent=2),
    })

    print("\n========== LLM 回复 ==========\n")
    print(result.content) # 模型回复


if __name__ == "__main__":
    main()