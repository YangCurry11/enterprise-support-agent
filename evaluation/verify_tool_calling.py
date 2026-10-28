"""Three turns through HTTP/ConversationService/LangGraph/SQLite, then stop at review.

Offline by default. Live requires --allow-remote and an explicit attempt budget;
only the pinned synthetic fixture is allowed. This module never approves a ticket.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit

from .evaluate_tool_calling import tool_environment, PROVENANCE
from .tool_calling_fakes import ScriptedQwen
from .sandbox import OTHER
from .run_evaluation import write_artifact, fingerprints
from .evaluators.reply_eval import facts
from support_agent.model_runtime import CallLedger, ModelSettings, model_calls

ROOT = Path(__file__).resolve().parents[1]
# Line endings are normalized by read_text; Git LF/CRLF does not change consent scope.
SYNTHETIC_HASHES = {
    "data/users.json": "af75c46aec09c5c3af9a9ba77da6db6c13f01dac50a8128da3187c630acbbefa",
    "data/orders.json": "43d7aefa45b408d86886edfbc3c712fdf82d283a86ec35d6f126c269ae91f1cf",
    "data/policies/after_sales_policy.md": "73f58c73b020e5c26ef8c762dcdc0541e8007fedaddda15be9ae6ed1560bb7a1",
    "data/policies/membership_policy.md": "ef497e37cc68971422a951d380fb898b7f1c835c277716c4ec826c2f615adecd",
    "data/policies/refund_policy.md": "bed915bbd81bb7e02e91b66b94c3e6d5dff322b643b613eaafc0c208b92d12db",
    "data/policies/shipping_policy.md": "0c3668c410b6476030c4fca2ba2c5e8e244d7a35947da7090fa4bb1657734215",
}


class _AcceptanceStopped(Exception):
    """Local check failure, not a provider exception; preserve the partial report."""


def _reply_checks(result, index):
    trace = result.get("tool_calling_trace", {})
    return {f"turn_{index}_tool_model_generated": trace.get("status") == "model_generated" and not trace.get("fallback_used"),
            f"turn_{index}_facts": all(facts(result)[0].values()),
            f"turn_{index}_used_real_protocol": trace.get("model_calls", {}).get("actual_model_calls", 0) >= 2}


def check_synthetic_sources(root=ROOT):
    policy_files = {p.relative_to(root).as_posix() for p in (root / "data/policies").glob("*.md")}
    if policy_files != {p for p in SYNTHETIC_HASHES if p.startswith("data/policies/")}:
        raise ValueError("Synthetic policy file set changed; stop before external data transfer")
    for relative, expected in SYNTHETIC_HASHES.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest() != expected:
            raise ValueError("Synthetic fixture changed; requires a new data review before live")
    return {"synthetic_fixture_matches": True, "external_data_scope":
            "fixed test questions, masked authorized order fields and retrieved synthetic policy chunks; no history, owner, phone, address, payment or existing database"}


def verify(*, live=False, ledger=None):
    from support_agent import app as api, business_db
    from support_agent.runtime import WorkflowService
    if live:
        if ledger is None or not 1 <= ledger.limit <= 8 or ledger.simulated:
            raise ValueError("Live requires an explicit non-simulated global budget of 1..8")
        check_synthetic_sources()
    ledger = ledger or CallLedger(8, simulated=True)
    fake = None if live else ScriptedQwen()
    results, checks, error = [], {}, None
    stage = "conversation"
    def require(**values):
        checks.update(values)
        if not all(checks.values()):
            raise _AcceptanceStopped()
    started = time.perf_counter()
    with tool_environment(live=live, model=fake) as box, model_calls(ledger):
        try:
            cid = box.conversation()
            stage = "turn_1"
            first = box.message(cid, "我的订单 ORD1001 到哪了？")
            results.append(first)
            require(**_reply_checks(first, 1),
                    turn_1_context=first["conversation_id"] == cid and first["order_id"] == "ORD1001",
                    first_tool_order=first.get("tool_results", {}).get("query_order", {}).get("ok") is True,
                    no_ticket=business_db.list_tickets() == [])
            stage = "turn_2"
            second = box.message(cid, "那它可以退款吗？")
            results.append(second)
            require(**_reply_checks(second, 2),
                    turn_2_context=second["conversation_id"] == cid and second["order_id"] == "ORD1001" and second["run_id"] != first["run_id"],
                    policy_source="refund_policy.md" in {d["source"] for d in second["retrieved_docs"]},
                    policy_tools={t["tool"] for t in second["tool_calling_trace"].get("tools", [])} == {"query_order", "search_policy"},
                    unknown_receipt=second.get("tool_results", {}).get("query_order", {}).get("facts", {}).get("receipt", {}).get("state") == "unknown",
                    no_ticket=business_db.list_tickets() == [])
            stage = "turn_3"
            key = str(uuid.uuid4())
            third = box.message(cid, "那帮我申请售后吧。", key)
            results.append(third)
            checks.update(same_conversation=all(r["conversation_id"] == cid for r in results),
                          independent_runs=len({r["run_id"] for r in results}) == 3,
                          confirmed_order=all(r["order_id"] == "ORD1001" for r in results),
                          first_tool_order=first.get("tool_results", {}).get("query_order", {}).get("ok") is True,
                          policy_source="refund_policy.md" in {d["source"] for d in second["retrieved_docs"]},
                          policy_tools={t["tool"] for t in second["tool_calling_trace"].get("tools", [])} == {"query_order", "search_policy"},
                          unknown_receipt=second.get("tool_results", {}).get("query_order", {}).get("facts", {}).get("receipt", {}).get("state") == "unknown",
                          no_ticket=business_db.list_tickets() == [],
                          original_review=third["status"] == "awaiting_review" and third["pending"][0]["kind"] == "approval",
                          high_risk_guard=third["tool_calling_trace"].get("status") == "guarded_workflow")
            require()
            stage = "post_review_checks"
            attempts = len(ledger.calls)
            resent = box.message(cid, "那帮我申请售后吧。", key)
            factory = api.app.state.workflows.tools_factory
            api.app.state.workflows = WorkflowService(box.root, tools_factory=factory)
            restored = box.json("GET", f"/agent/runs/{third['run_id']}")
            endpoint = f"/agent/runs/{third['run_id']}/review"
            checks.update(customer_cannot_approve=box.call("POST", endpoint, {"approved": True}).status_code == 403,
                          other_customer_denied=box.call("GET", f"/agent/conversations/{cid}/messages", token=OTHER).status_code == 404,
                          sqlite_pending_restored=restored["status"] == "awaiting_review" and restored["run_id"] == third["run_id"],
                          replay_same_run=resent["run_id"] == third["run_id"],
                          no_replay_or_review_model_calls=len(ledger.calls) == attempts,
                          still_no_ticket=business_db.list_tickets() == [])
            require()
        except _AcceptanceStopped:
            error = "acceptance_check_failed"
        except Exception as exc:
            checks["execution"] = False
            error = type(exc).__name__  # No provider body, requests or exception message in report.
        row = {"id": "tool-three-turn-e2e", "input": "订单 → 指代退款 → 售后原审核（不批准）", "checks": checks,
               "passed": bool(checks) and all(checks.values()), "error_type": error, "results": results,
               "failure_stage": stage if error else None, "stopped_after_turn": len(results) if error else None,
               "latency_ms": (time.perf_counter() - started) * 1000, "manual_review_status": "pending"}
    return {"execution_mode": "live_qwen_tool_protocol" if live else "offline_scripted_protocol",
            "metrics": {"sample_count": 1, "passed": int(row["passed"])}, "cases": [row],
            "model_calls": ledger.summary(), "data_provenance": PROVENANCE,
            "database_isolation": "TemporaryDirectory, original demonstration databases untouched; no approval/write"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--allow-remote", action="store_true", help="明确授权仅发送固定合成数据到配置的千问聊天服务")
    parser.add_argument("--max-model-calls", type=int, help="live 必填；全三轮累计1..8次请求尝试（含重试）")
    parser.add_argument("--check-config", action="store_true", help="只读取配置及合成数据指纹；不创建客户端、不发送请求")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "reports-tool-e2e")
    args = parser.parse_args(argv)
    if args.mode == "live" and not args.check_config and (not args.allow_remote or args.max_model_calls is None):
        parser.error("Live requires --allow-remote and explicit --max-model-calls; nothing sent")
    if args.max_model_calls is not None and not 1 <= args.max_model_calls <= 8:
        parser.error("--max-model-calls must be in 1..8")
    settings = None
    try:
        data_check = check_synthetic_sources()
        if args.mode == "live" or args.check_config:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            settings = ModelSettings.read()
            host = urlsplit(settings.base_url).hostname or ""
            official_host = host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"} or host.endswith(".maas.aliyuncs.com")
            if not settings.model.lower().startswith("qwen") or not official_host:
                raise ValueError("This acceptance command requires an official DashScope Qwen endpoint/model")
    except ValueError as exc:
        parser.error(str(exc))
    if args.check_config:
        print(json.dumps({"configuration": settings.public(), **data_check, "network_calls": 0,
                          "overrides": {"tool_calling": True, "intent_model": False, "retries": 0, "embedding": False}}, ensure_ascii=False))
        return 0
    ledger = CallLedger(args.max_model_calls or 8, simulated=args.mode == "offline")
    result = verify(live=args.mode == "live", ledger=ledger)
    report = {"schema_version": 3, "generated_at": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
              "data_provenance": PROVENANCE, "configuration": settings.public() if settings else None,
              **data_check, **fingerprints(), "e2e": result, "model_calls": ledger.summary()}
    write_artifact(report, args.output.resolve())
    # response_mode() in the old writer describes the legacy node only. Export a
    # specific table for Tool Calling so it is never mislabeled as legacy generation.
    (args.output.resolve() / "tool_review.json").write_text(json.dumps({"review_status": "pending",
        "scope": "new tool_calling_trace, not old LLMResponseAgent", "results": result["cases"][0]["results"]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "mode": args.mode, "passed": result["metrics"]["passed"],
                      "model_calls": ledger.summary()}, ensure_ascii=False))
    return 0 if result["metrics"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
