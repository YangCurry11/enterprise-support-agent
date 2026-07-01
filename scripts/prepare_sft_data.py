"""生成一份 Agent 数据清洗/标注样例。

真实工作中这类数据可用于：
1. 意图识别评估集
2. Tool Calling 选择评估集
3. SFT / LoRA 数据准备
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = BASE_DIR / "data" / "training" / "customer_intent_dataset.jsonl"

examples = [
    {"user_input": "我的订单 ORD1001 到哪了？", "intent": "order_query", "required_tool": "query_order", "slots": {"order_id": "ORD1001"}, "response_type": "order_status_reply"},
    {"user_input": "ORD1002 怎么还没发货？", "intent": "order_query", "required_tool": "query_order", "slots": {"order_id": "ORD1002"}, "response_type": "shipping_delay_reply"},
    {"user_input": "我买了10天还能退吗？", "intent": "refund_policy", "required_tool": "search_policy", "slots": {"received_days": 10}, "response_type": "policy_explanation"},
    {"user_input": "超过七天无理由还能退款吗", "intent": "refund_policy", "required_tool": "search_policy", "slots": {"received_days": 8}, "response_type": "policy_explanation"},
    {"user_input": "商品坏了，无法使用", "intent": "after_sales", "required_tool": "create_ticket", "slots": {"quality_issue": True}, "response_type": "create_after_sales_ticket"},
    {"user_input": "少发了配件怎么办", "intent": "after_sales", "required_tool": "create_ticket", "slots": {"issue": "missing_parts"}, "response_type": "create_after_sales_ticket"},
    {"user_input": "物流三天没有更新", "intent": "shipping_policy", "required_tool": "search_policy", "slots": {"issue": "logistics_not_updated"}, "response_type": "shipping_policy_reply"},
    {"user_input": "我要投诉你们", "intent": "complaint", "required_tool": "create_ticket", "slots": {}, "response_type": "complaint_escalation"},
    {"user_input": "帮我转人工", "intent": "human_escalation", "required_tool": "create_ticket", "slots": {}, "response_type": "human_transfer"},
    {"user_input": "你好", "intent": "chit_chat", "required_tool": "none", "slots": {}, "response_type": "greeting"},
]


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for item in examples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"已生成：{OUT_PATH}")


if __name__ == "__main__":
    main()
