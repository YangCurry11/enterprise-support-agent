"""确定性最小事实防线；不是完整语义裁判，仍需要独立人工复核。"""
import re
from .order_facts import build_order_facts


# 最小断言识别只提取签收极性/天数；是否有证据由统一业务事实判断，
# 不把“尚未签收”这句话一律禁掉（明确未签收时允许），也不误禁条件句。
_RECEIPT_CLAIM = re.compile(
    r"(?P<polarity>尚未|还未|仍未|并未|没有|还没|未|没|已经|现已|已|完成)"
    r"(?:完成)?(?:签收|收货|收到(?:货物|商品|包裹|货))(?:[了\s]*(?P<days>\d+)\s*天)?"
    r"|(?:签收|收货)(?:已经|已有|了)?(?P<bare_days>\d+)\s*天"
)


def _receipt_claims(text):
    for clause in re.split(r"[，,。；;！？!?\n]|但是|不过|然而|但", text):
        for match in _RECEIPT_CLAIM.finditer(clause):
            before, after = clause[:match.start()], clause[match.end():]
            conditional = any(word in before for word in ("如果", "假如", "假设", "倘若", "若"))
            uncertain = any(word in before for word in ("是否", "请问", "无法确认", "不能确认", "无法确定", "不能确定", "不确定", "尚不清楚", "需核实", "未能确认"))
            if conditional or uncertain or after.lstrip("了 ").startswith(("后", "时", "内", "的话", "则", "吗", "么")):
                continue
            state = "received" if match.group("polarity") in {None, "已", "已经", "现已", "完成"} else "not_received"
            days = match.group("days") or match.group("bare_days")
            yield state, int(days) if days is not None else None


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
    receipt = build_order_facts(order).receipt
    for state, days in _receipt_claims(text):
        if state != receipt.state:
            errors.append("unsupported_receipt_state")
        if days is not None and days != receipt.received_days:
            errors.append("unsupported_received_days")
    return list(dict.fromkeys(errors))
