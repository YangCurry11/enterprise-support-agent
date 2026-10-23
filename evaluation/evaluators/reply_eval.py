"""真实图上的回复/业务事实检查；语言质量另交人工复核，不伪称语义准确率。"""
from contextlib import nullcontext
import time
from unittest.mock import patch
from ..sandbox import sandbox
from .metrics import timing_metrics


def response_mode(result):
    detail = next((step["detail"] for step in reversed(result.get("steps", []))
                   if step["name"] == "LLMResponseAgent"), {})
    return detail.get("mode", "deterministic"), detail


def facts(result):
    from support_agent.reply_safety import reply_violations
    order = result.get("tool_results", {}).get("query_order", {})
    ticket = result.get("tool_results", {}).get("create_ticket", {})
    pending = result.get("status") in {"awaiting_review", "awaiting_input"}
    violations = reply_violations(result.get("final_response", ""), order.get("data") if order.get("ok") and not pending else None,
                                  result.get("retrieved_docs") if not pending else None, ticket.get("data") if ticket.get("ok") else None)
    return {"nonempty_response": bool(result.get("final_response")), "minimal_fact_checks": not violations,
            "receipt_facts_consistent": not {"unsupported_receipt_state", "unsupported_received_days"}.intersection(violations)}, violations


def evaluate(cases, live=False):
    from support_agent import business_db
    from support_agent.scoped_tools import ScopedTools
    rows = []
    for case in cases:
        started = time.perf_counter()
        results, checks, error, violations = [], {}, None, []
        with sandbox(live=live, intent_live=False) as box:
            try:
                cid = box.conversation()
                scenario = case["scenario"]
                if scenario == "missing_logistics":
                    with business_db.get_connection() as connection:
                        connection.execute("UPDATE orders SET tracking_number='',logistics_company='',estimated_delivery='' WHERE order_id='ORD1001'")
                if scenario in {"policy_followup", "after_sales", "foreign_order"}:
                    first = box.message(cid, "我的订单 ORD1001 到哪了？")
                    results.append(first)
                guard = patch.object(ScopedTools, "query_order", return_value={"ok": False, "code": "tool_unavailable", "error": "模拟读取失败"}) if scenario == "tool_error" else nullcontext()
                with guard:
                    result = box.message(cid, case["text"])
                results.append(result)
                checks, violations = facts(result)
                if scenario in {"order", "missing_logistics"}:
                    checks.update(completed=result["status"] == "completed", authorized_order=result["tool_results"]["query_order"]["ok"])
                    if scenario == "missing_logistics":
                        checks["no_invented_tracking"] = "SF123456789" not in result["final_response"]
                elif scenario == "tool_error":
                    checks.update(tool_error_preserved=not result["tool_results"]["query_order"]["ok"],
                                  no_false_order_success="已发货" not in result["final_response"],
                                  no_reply_model=response_mode(result)[0] == "deterministic")
                elif scenario == "policy_followup":
                    checks.update(confirmed_order=result["order_id"] == first["order_id"] == "ORD1001",
                                  new_run=result["run_id"] != first["run_id"],
                                  reauthorized=any(c["tool"] == "query_order" and c["run_id"] == result["run_id"] and c["ok"] for c in box.tool_calls),
                                  policy_source="refund_policy.md" in {doc["source"] for doc in result["retrieved_docs"]},
                                  cited_source="refund_policy.md" in result["final_response"])
                elif scenario == "after_sales":
                    checks.update(order_reference=result["order_id"] == "ORD1001", waiting_review=result["status"] == "awaiting_review",
                                  original_interrupt=bool(result["pending"]) and result["pending"][0]["kind"] == "approval",
                                  no_ticket_before_review=business_db.list_tickets() == [],
                                  customer_cannot_approve=box.call("POST", f"/agent/runs/{result['run_id']}/review", {"approved": True}).status_code == 403)
                elif scenario == "foreign_order":
                    checks.update(order_denied=not result["tool_results"]["query_order"]["ok"],
                                  no_foreign_product="机械键盘" not in str(result),
                                  no_foreign_owner="U1002" not in str(result), no_ticket=business_db.list_tickets() == [],
                                  no_reply_model=response_mode(result)[0] == "deterministic")
                else:
                    raise ValueError("unsupported_scenario")
                expected_generated = results if scenario in {"order", "missing_logistics", "policy_followup"} else results[:-1]
                if live:
                    checks["expected_live_replies_generated"] = all(response_mode(r)[0] == "llm_generated" for r in expected_generated)
            except Exception as exc:
                checks["execution"] = False
                error = type(exc).__name__  # 不保存异常正文或供应商原文
            result = results[-1] if results else {}
            mode, detail = response_mode(result)
            rows.append({"id": case["id"], "input": case["text"], "scenario": case["scenario"],
                         "passed": bool(checks) and all(checks.values()), "checks": checks, "violations": violations,
                         "error_type": error or detail.get("error"), "response_mode": mode,
                         "response": result.get("final_response", ""), "run_id": result.get("run_id"),
                         "status": result.get("status"), "results": results, "tool_calls": box.tool_calls,
                         "requests": box.requests, "model_used": mode == "llm_generated",
                         "fallback_used": any(response_mode(r)[0] == "fallback_template" for r in results),
                         "model_fact_violations": detail.get("model_trace", {}).get("fact_violations", []),
                         "latency_ms": (time.perf_counter() - started) * 1000,
                         "manual_review_status": "pending", "execution_mode": "live" if live else "offline"})
    passed = sum(row["passed"] for row in rows)
    return {"execution_mode": "live" if live else "offline", "cases": rows,
            "metrics": {"sample_count": len(rows), "passed": passed, "failed": len(rows) - passed,
                        "pass_rate": passed/len(rows) if rows else None,
                        "generated_reply_count": sum(response_mode(r)[0] == "llm_generated" for row in rows for r in row["results"]),
                        "fallback_count": sum(response_mode(r)[0] == "fallback_template" for row in rows for r in row["results"]),
                        "timing": timing_metrics([row["latency_ms"] for row in rows]), "manual_reviewed": 0},
            "limitations": "确定性事实/权限/状态检查，不是完整语义正确率；语气、政策解释、清晰度必须独立人工复核"}
