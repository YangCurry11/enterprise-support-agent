"""Opt-in local diagnosis. Unknown text is projected away, never logged verbatim."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import threading
import uuid
from itertools import islice

from .config import BASE_DIR

_lock = threading.Lock()
# Only fixed non-identifying vocabulary survives. Names, IDs, numbers, keys,
# addresses and arbitrary text cannot be preserved by a blacklist omission.
_terms = ("订单", "物流", "单号", "状态", "已发货", "尚未签收", "还未签收", "未签收", "已签收", "签收",
          "未知", "无法确认", "不能确认", "是否", "如果", "假如", "若", "不代表", "不意味着", "不表示",
          "审批", "审核", "通过", "已通过", "支付", "付款", "退款", "退货", "成功", "已成功", "赔偿", "到账",
          "预计", "送达", "签收时间", "天数", "当前", "暂无", "核实", "需要", "条件", "符合", "满足")
_projection = re.compile("|".join(re.escape(t) for t in sorted(_terms, key=len, reverse=True)))
_codes = {"unsupported_order", "missing_order_id", "missing_status", "missing_tracking_number",
          "unsupported_tracking_number", "unsupported_source", "missing_source", "missing_ticket_id",
          "unsupported_financial_action", "unsupported_ticket_action", "unsupported_receipt_state",
          "unsupported_received_days", "unsupported_payment_action", "unsupported_approval_action",
          "unsupported_refund_eligibility"}


def project_reply(text):
    """Lossy term-order projection, NOT recoverable raw response or a PII guarantee for raw text."""
    result, cursor = [], 0
    for match in _projection.finditer(text[:6000]):
        if match.start() > cursor:
            result.append("〈隐藏〉")
        result.append(match.group())
        cursor = match.end()
    if cursor < len(text[:6000]):
        result.append("〈隐藏〉")
    return "".join(result)[:2000]


def record_rejection(candidate, violations, summary, run_id):
    flag = os.getenv("LLM_REPLY_DIAGNOSTICS_ENABLED", "false").lower()
    if flag != "true":
        return {"enabled": False, "recorded": False, "status": "disabled" if flag == "false" else "invalid_setting"}
    result = {"enabled": True, "recorded": False, "status": "unavailable"}
    try:
        with _lock:
            root = BASE_DIR.resolve()
            directory = root / ".local_diagnostics" / "reply_safety"
            for part in (directory.parent, directory):
                if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                    return result
            directory.resolve().relative_to(root)
            directory.mkdir(parents=True, exist_ok=True)
            if len(list(islice(directory.glob("*.json"), 50))) >= 50:
                return {**result, "status": "limit_reached"}
            summary = summary if isinstance(summary, dict) else {}
            flags = summary.get("required_fields_present", {})
            flags = flags if isinstance(flags, dict) else {}
            receipt = summary.get("receipt_state")
            safe_summary = {
                "receipt_state": receipt if isinstance(receipt, str) and receipt in {"received", "not_received", "unknown"} else "unknown",
                "required_fields_present": {k: flags[k] for k in ("order_id", "status", "tracking_number") if type(flags.get(k)) is bool},
                "policy_source_present": summary.get("policy_source_present") if type(summary.get("policy_source_present")) is bool else None}
            # No arbitrary model text, tool payload, identity, credentials or path in the record.
            record = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                      "run_hash": hashlib.sha256(str(run_id).encode()).hexdigest()[:16],
                      "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                      "candidate_chars": len(candidate), "projection_is_lossy": True,
                      "candidate_projection": project_reply(candidate),
                      "violations": [code if isinstance(code, str) and code in _codes else "unclassified_violation" for code in violations],
                      "facts_summary": safe_summary}
            path = directory / (uuid.uuid4().hex + ".json")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, allow_nan=False, indent=2)
            return {**result, "recorded": True, "status": "saved_locally"}
    except (OSError, ValueError, TypeError):
        return result  # Diagnosis must never disable rejection or its template fallback.
