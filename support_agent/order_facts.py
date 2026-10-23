"""从本轮授权工具记录构造事实；不把空值或发货状态推断成签收结论。"""
from typing import Any, Literal, Mapping
from pydantic import BaseModel, ConfigDict, Field


class ReceiptFacts(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: Literal["received", "not_received", "unknown"]
    received_days: int | None = Field(default=None, ge=0, strict=True)
    evidence: list[str] = Field(default_factory=list)
    conflicting_evidence: bool = False


class OrderFacts(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str | None
    order_status: str | None
    receipt: ReceiptFacts
    logistics: dict[str, str | None]
    refund_eligibility: Literal["not_determined"] = "not_determined"
    unknown_fields: list[str]


def _text(value):
    return (value.strip() or None) if isinstance(value, str) else None


def build_order_facts(order: Mapping[str, Any] | None) -> OrderFacts:
    """只用明确签收状态或合法签收天数；历史、预计送达、模型facts都不作为证据。"""
    raw = order or {}
    status = _text(raw.get("status"))
    raw_days = raw.get("received_days")
    # 0表示今天签收，不能用真值判断；负数、bool、字符串不冒充合法天数。
    days = raw_days if type(raw_days) is int and raw_days >= 0 else None
    received = status in {"已签收", "已收货"} or days is not None
    not_received = status in {"未签收", "未收货"}
    conflict = received and not_received
    state = "unknown" if conflict else "received" if received else "not_received" if not_received else "unknown"
    evidence = []
    if status in {"已签收", "已收货", "未签收", "未收货"}:
        evidence.append("order.status")
    if days is not None:
        evidence.append("order.received_days")
    receipt = ReceiptFacts(state=state, received_days=None if conflict else days,
                           evidence=evidence, conflicting_evidence=conflict)
    logistics = {name: _text(raw.get(name)) for name in ("logistics_company", "tracking_number", "estimated_delivery")}
    unknown = ["refund_eligibility"]  # 签收/时间条件不等于商品完好、材料齐全或审核通过。
    if state == "unknown":
        unknown.append("receipt.state")
    if receipt.received_days is None:
        unknown.append("receipt.received_days")
    unknown.extend("logistics." + name for name, value in logistics.items() if value is None)
    return OrderFacts(order_id=_text(raw.get("order_id")), order_status=status, receipt=receipt,
                      logistics=logistics, unknown_fields=unknown)


def receipt_summary(facts: OrderFacts) -> str:
    """用于确定性模板；与模型使用同一事实，不将未知签收天数当成0。"""
    receipt = facts.receipt
    if receipt.conflicting_evidence:
        return "签收记录存在冲突，无法确认是否签收及签收时间，请人工核实。"
    if receipt.state == "unknown":
        return "目前无法确认是否签收及签收时间，请补充实际签收情况；政策是否适用仍需核实。"
    if receipt.state == "not_received":
        return "工具明确记录未签收；具体政策适用仍需结合实际业务情况核实。"
    if receipt.received_days is None:
        return "工具已确认签收，但签收天数未知，请补充具体签收日期以核实政策条件。"
    return f"工具记录已签收{receipt.received_days}天；这项时间事实不代表其他退货退款条件已满足。"
