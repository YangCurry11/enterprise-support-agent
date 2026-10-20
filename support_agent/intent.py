#判断用户问题属于什么类型，并尽量提取订单号
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re # 正则表达式 提取特定格式的内容


INTENT_ORDER = "order_query"
INTENT_REFUND = "refund_policy" # 退款政策
INTENT_SHIPPING = "shipping_policy" # 物流政策
INTENT_AFTER_SALES = "after_sales" # 售后政策
INTENT_COMPLAINT = "complaint" # 投诉
INTENT_HUMAN = "human_escalation" # 人工处理
INTENT_CHITCHAT = "chit_chat"  # 闲聊
INTENT_UNKNOWN = "unknown" # 未知

ORDER_ID_PATTERN = re.compile(r"\bORD\d{4,}\b", re.IGNORECASE) # 订单号提取格式 re.IGNORECASE：忽略大小写


@dataclass
class IntentResult:
    intent: str
    order_id: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""


def extract_order_id(text: str) -> Optional[str]: # 提取订单号
    match = ORDER_ID_PATTERN.search(text or "")
    return match.group(0).upper() if match else None # 转换为大写 .upper()：转大写


def classify_intent(text: str) -> IntentResult:
    """规则版意图识别。后续可替换为 LLM JSON 结构化输出。"""
    text = text.strip() # 去除前后空格
    lower = text.lower() # 转换为小写
    order_id = extract_order_id(text) # 提取订单号

    human_words = ["人工", "真人", "客服", "投诉", "生气", "赔偿", "举报"]
    complaint_words = ["投诉", "太差", "生气", "垃圾", "欺骗", "赔偿"]
    refund_words = ["退", "退款", "退货", "无理由", "7天", "七天", "换货", "退费", "申请退款", "不想要了"]
    shipping_words = ["物流", "快递", "发货", "到哪", "没到", "配送", "单号", "送达"]
    after_sales_words = ["坏", "坏了", "无法使用", "维修", "售后", "少件", "错发", "破损"]
    order_words = ["订单", "ord", "买的", "商品状态"]

    if any(w in lower for w in complaint_words):
        return IntentResult(INTENT_COMPLAINT, order_id, 0.90, "命中投诉/强烈情绪关键词")
    if any(w in lower for w in human_words):
        return IntentResult(INTENT_HUMAN, order_id, 0.85, "用户要求人工或存在高风险情绪")
    if any(w in lower for w in refund_words):
        return IntentResult(INTENT_REFUND, order_id, 0.82, "命中退款/退货政策关键词")
    if any(w in lower for w in after_sales_words):
        return IntentResult(INTENT_AFTER_SALES, order_id, 0.82, "命中售后关键词")
    if any(w in lower for w in ["政策", "规定", "多久发货", "发货时效"]) and any(w in lower for w in shipping_words):
        return IntentResult(INTENT_SHIPPING, order_id, 0.82, "物流政策咨询")
    if order_id or any(w in lower for w in order_words + shipping_words):
        return IntentResult(INTENT_ORDER, order_id, 0.82, "命中订单/物流查询关键词")
    if len(text) <= 8 and any(w in lower for w in ["你好", "您好", "在吗"]):
        return IntentResult(INTENT_CHITCHAT, order_id, 0.7, "简单寒暄")
    return IntentResult(INTENT_UNKNOWN, order_id, 0.45, "未命中明确规则")
