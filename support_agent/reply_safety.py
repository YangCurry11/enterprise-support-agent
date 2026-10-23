"""确定性最小事实防线；不是完整语义裁判，仍需要独立人工复核。"""
import re


def reply_violations(text, order=None, documents=None, ticket=None):
    errors = []
    known_order = (order or {}).get("order_id")
    if set(re.findall(r"ORD\d{4,}", text, re.I)) - ({known_order} if known_order else set()):
        errors.append("unsupported_order")
    if order:
        for name in ("order_id", "status"):
            if order.get(name) and str(order[name]) not in text:
                errors.append("missing_" + name)
        # 订单查询有已知物流时不能省略/改写真实单号；政策回答不强求重复单号。
        if not documents and order.get("tracking_number") and order["tracking_number"] not in text:
            errors.append("missing_tracking_number")
    allowed_tracking = {(order or {}).get("tracking_number", "")}
    if set(re.findall(r"\b(?:SF|JD|ZT|YT|ST)\d{6,}\b", text, re.I)) - allowed_tracking:
        errors.append("unsupported_tracking_number")
    sources = {doc["source"] for doc in documents or []}
    cited = set(re.findall(r"[A-Za-z0-9_-]+\.md", text))
    if cited - sources:
        errors.append("unsupported_source")
    if sources and not sources.intersection(cited):
        errors.append("missing_source")
    if ticket and ticket.get("ticket_id") and ticket["ticket_id"] not in text:
        errors.append("missing_ticket_id")
    financial_text = re.sub(r"(?:不代表|不意味着|不表示)(?:退款|赔偿)(?:已经|已)?(?:获批准|批准|通过|到账|完成)", "", text)
    if re.search(r"(?:已为您|已经|已成功|成功)(?:完成)?(?:退款|赔偿|退费)|(?:退款|赔偿)(?:申请)?(?:已经|已)(?:批准|通过|到账|完成)", financial_text):
        errors.append("unsupported_financial_action")
    if not ticket and re.search(r"(?:已|已经)(?:为您)?创建.{0,8}工单", text):
        errors.append("unsupported_ticket_action")
    return errors
