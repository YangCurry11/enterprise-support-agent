"""固定回复的签收事实回归，不调用模型，不声称真实千问效果。"""
import time
from support_agent.order_facts import build_order_facts
from .reply_eval import facts


def evaluate(cases):
    rows = []
    for case in cases:
        started = time.perf_counter()
        normalized = build_order_facts(case["order"]).model_dump()
        result = {"status": "completed", "final_response": case["reply"],
                  "tool_results": {"query_order": {"ok": True, "data": case["order"], "facts": normalized}},
                  "retrieved_docs": [{"source": "refund_policy.md"}]}
        observed_checks, violations = facts(result)
        checks = {"expected_receipt_state": normalized["receipt"]["state"] == case["expected_state"],
                  "expected_validation": set(violations) == set(case["expected_violations"]),
                  "receipt_check_consistent": observed_checks["receipt_facts_consistent"] == (
                      not {"unsupported_receipt_state", "unsupported_received_days"}.intersection(violations))}
        rows.append({"id": case["id"], "input": case["reply"], "passed": all(checks.values()), "checks": checks,
                     "facts": normalized, "expected_violations": case["expected_violations"], "violations": violations,
                     "latency_ms": (time.perf_counter() - started) * 1000})
    return {"execution_mode": "offline_fact_regression", "cases": rows,
            "metrics": {"sample_count": len(rows), "passed": sum(row["passed"] for row in rows), "actual_model_calls": 0},
            "limitations": "固定合成回复的确定性边界回归，非真实模型或完整语义正确率；错误文本被正确拦截也计为场景通过"}
