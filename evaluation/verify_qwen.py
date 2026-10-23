"""三轮 + 原审批接口的显式验证入口；默认离线，live 必须给物理请求预算。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
from .sandbox import sandbox, REVIEWER, OTHER
from .evaluators.reply_eval import facts, response_mode
from support_agent.model_runtime import CallLedger, ModelSettings, ModelConfigError, model_calls


def verify(*, live=False, ledger=None):
    from support_agent import app as api, business_db
    from support_agent.runtime import WorkflowService
    ledger = ledger or CallLedger(8)
    results, checks, error = [], {}, None
    started = time.perf_counter()
    with sandbox(live=live, intent_live=live) as box, model_calls(ledger):
        cid = box.conversation()
        try:
            first = box.message(cid, "我的订单 ORD1001 到哪了？")
            results.append(first)
            second = box.message(cid, "那它可以退款吗？")
            results.append(second)
            key = str(uuid.uuid4())
            third = box.message(cid, "那帮我申请售后吧。", key)
            results.append(third)
            checks.update(order_tool=first["tool_results"]["query_order"]["ok"],
                          correct_intents=[r["intent"] for r in results] == ["order_query", "refund_policy", "after_sales"],
                          confirmed_order=all(r["order_id"] == "ORD1001" for r in results),
                          independent_runs=len({r["run_id"] for r in results}) == 3,
                          same_conversation=all(r["conversation_id"] == cid for r in results),
                          policy_source="refund_policy.md" in {d["source"] for d in second["retrieved_docs"]},
                          order_rechecked=any(c["tool"] == "query_order" and c["run_id"] == second["run_id"] and c["ok"] for c in box.tool_calls),
                          awaiting_original_review=third["status"] == "awaiting_review" and third["pending"][0]["kind"] == "approval",
                          no_ticket_before_review=business_db.list_tickets() == [])
            for index, result in enumerate(results[:2], 1):
                fact_checks, _ = facts(result)
                checks[f"turn_{index}_fact_checks"] = all(fact_checks.values())
                if live:
                    checks[f"turn_{index}_really_generated"] = response_mode(result)[0] == "llm_generated"
            endpoint = f"/agent/runs/{third['run_id']}/review"
            checks["customer_cannot_approve"] = box.call("POST", endpoint, {"approved": True}).status_code == 403
            checks["other_customer_denied"] = box.call("GET", f"/agent/conversations/{cid}/messages", token=OTHER).status_code == 404
            # 重建服务，验证恢复来自 SQLite 检查点而不是内存变量。
            factory = api.app.state.workflows.tools_factory
            api.app.state.workflows = WorkflowService(box.root, tools_factory=factory)
            completed = box.json("POST", endpoint, {"approved": True, "note": "隔离模拟数据验证，不是真实退款审批"}, REVIEWER)
            results.append(completed)
            count = len(ledger.calls)
            repeated = box.json("POST", endpoint, {"approved": True}, REVIEWER)
            resent = box.message(cid, "那帮我申请售后吧。", key)
            history = box.json("GET", f"/agent/conversations/{cid}/messages")["messages"]
            tickets = business_db.list_tickets()
            checks.update(completed_after_review=completed["status"] == "completed",
                          exactly_one_ticket=len(tickets) == 1 and tickets[0]["order_id"] == "ORD1001",
                          same_run_after_resume=third["run_id"] == completed["run_id"] == repeated["run_id"] == resent["run_id"],
                          six_persistent_messages=len(history) == 6,
                          latest_message_updated=history[-1]["content"] == completed["final_response"],
                          no_replay_model_calls=len(ledger.calls) == count,
                          ticket_not_refund="不代表退款或赔偿已获批准" in completed["final_response"])
        except Exception as exc:
            checks["execution"] = False
            error = type(exc).__name__
        row = {"id": "three-turn-e2e", "input": "订单查询 → 指代退款政策 → 售后审核 → 原接口批准",
               "passed": bool(checks) and all(checks.values()), "checks": checks, "error_type": error,
               "conversation_id": cid, "results": results, "requests": box.requests, "tool_calls": box.tool_calls,
               "latency_ms": (time.perf_counter() - started) * 1000,
               "execution_mode": "live" if live else "offline", "manual_review_status": "pending"}
    return {"execution_mode": "live" if live else "offline", "cases": [row],
            "metrics": {"sample_count": 1, "passed": int(row["passed"]), "failed": int(not row["passed"])},
            "model_calls": ledger.summary(), "database_isolation": "TemporaryDirectory; no persistent demonstration DB writes"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "reports-e2e")
    args = parser.parse_args(argv)
    if args.mode == "live" and args.max_model_calls is None:
        parser.error("三轮 live 必须明确 --max-model-calls（包含意图、回复和重试）")
    try:
        ledger = CallLedger(args.max_model_calls if args.max_model_calls is not None else 8)
        if args.mode == "live":
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
            settings = ModelSettings.read()
        else:
            settings = None
    except (ValueError, ModelConfigError) as exc:
        parser.error(str(exc))
    result = verify(live=args.mode == "live", ledger=ledger)
    from .run_evaluation import write_artifact, fingerprints
    report = {"schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
              "data_provenance": "AI-assisted synthetic development scenarios; NOT independently human-reviewed",
              "configuration": settings.public() if settings else None,
              **fingerprints(),
              "e2e": result, "model_calls": ledger.summary()}
    write_artifact(report, args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["metrics"]["passed"],
                      "actual_model_calls": len(ledger.calls), "mode": args.mode}, ensure_ascii=False))
    return 0 if result["metrics"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
