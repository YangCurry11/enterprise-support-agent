"""python -m evaluation.run_evaluation；默认离线，报告只含模拟数据。"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
from .evaluators import intent_eval, rag_eval, workflow_eval, reply_eval, receipt_eval
from . import failure_checks
from support_agent.model_runtime import ModelSettings, ModelConfigError, CallLedger, model_calls

ROOT = Path(__file__).resolve().parent


def load(name):
    return [json.loads(line) for line in (ROOT/"datasets"/name).read_text(encoding="utf-8").splitlines() if line.strip()]


def fingerprints():
    return {"datasets": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"datasets").glob("*.jsonl"))},
            "source_hashes": {str(p.relative_to(ROOT.parent)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                              for directory in (ROOT, ROOT.parent/"support_agent") for p in sorted(directory.rglob("*.py"))},
            "policy_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent/"data"/"policies").glob("*.md"))}}


def csv_safe(value):
    # 模型文本是不可信数据，防止人工用Excel打开CSV时被识别为公式。
    return "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_artifact(report, output):
    """普通评测与独立三轮验证共用输出，不要求虚构不存在的组件指标。"""
    output.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    # 同目录临时文件 + 原子替换，API 不会读到半份报告。
    temporary = output/"latest.json.tmp"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output/"latest.json")
    components = [key for key, value in report.items() if isinstance(value, dict) and "cases" in value and "metrics" in value]
    with (output/"details.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["component","id","input","passed","latency_ms","detail"])
        writer.writeheader()
        for component in components:
            for row in report[component]["cases"]:
                values = {"component":component,"id":row["id"],"input":row["input"],"passed":row["passed"],
                          "latency_ms":row["latency_ms"],"detail":json.dumps(row,ensure_ascii=False)}
                writer.writerow({key: csv_safe(value) for key,value in values.items()})
    failures = [(key,row) for key in components for row in report[key]["cases"] if not row["passed"]]
    summary = ["# Agent 实际评测报告", "", f"生成时间：{report['generated_at']}；模式：{report['mode']}。", "",
               "数据为 AI 辅助编写的模拟开发标注，尚未经独立人工复核，不是实际客户数据或独立测试集。", "",
               "模式按组件记录：live 不意味着所有组件都联网；simulated_fault 为离线注入，不计入真实调用成功率。", ""]
    for key in components:
        metrics = report[key]["metrics"]
        summary += [f"## {key}（{report[key].get('execution_mode', 'offline')}）", ""]
        def number(value):
            return f"{value:.4f}" if isinstance(value, (int, float)) else "未统计"
        if key == "intent":
            summary += ["| 分类口径 | 样本数 | Accuracy | Macro-F1 |", "|---|---:|---:|---:|"]
            for name, values in (("同批规则基线", report[key]["rule_baseline"]), ("最终（含保护/回退）", metrics), ("原始模型成功子集", report[key]["raw_model_metrics"])):
                measured = values.get("sample_count", 0) > 0
                summary.append(f"| {name} | {values.get('sample_count', 0)} | {number(values.get('accuracy')) if measured else '未统计'} | {number(values.get('macro_f1')) if measured else '未统计'} |")
            summary += ["", f"审核保护 {metrics.get('guard_count', 0)} 题；模型成功 {metrics.get('model_success_count', 0)} 题；规则回退 {metrics.get('fallback_count', 0)} 题。", "",
                        "各类 Precision/Recall/F1 与混淆矩阵见 latest.json；原始模型子集不能与全样本直接比较。", "",
                        "raw_model_metrics 仅成功解析子集；final 指标包含 guard 与规则兜底，不能当作纯模型准确率。", ""]
        elif key == "rag":
            summary += [f"{metrics['sample_count']} 题；文档 Recall@1/3/5 = {number(metrics.get('recall_at_1'))} / {number(metrics.get('recall_at_3'))} / {number(metrics.get('recall_at_5'))}；MRR = {number(metrics.get('mrr'))}。", "",
                        "K为返回片段数，命中源文档不等于最终回答事实正确。", ""]
        else:
            summary += [f"符合预期 {metrics.get('passed', 0)} / {metrics.get('sample_count', 0)}。", ""]
            if key == "workflow":
                summary += [f"末态完成 {metrics.get('completed_scenarios', 0)} 场景；HTTP {metrics.get('request_success', 0)} / {metrics.get('request_total', 0)} 次2xx；工具拒绝/失败 {metrics.get('tool_denied_or_failed', 0)} 次。", "",
                            "等待审核、预期越权拒绝也可能是正确行为，不等于所有run都完成或客户问题都解决。", ""]
            if key == "reply":
                summary += [f"实际生成 {metrics.get('generated_reply_count', 0)} 条，模板回退 {metrics.get('fallback_count', 0)} 条；人工已复核 {metrics.get('manual_reviewed', 0)} 条。", ""]
            if key == "faults":
                summary += [f"真实供应商请求 {metrics.get('actual_provider_calls', 0)} 次；本地模拟调用 {metrics.get('simulated_model_calls', 0)} 次。", ""]
            if key == "receipt":
                summary += ["固定合成文本的签收三态/天数回归；错误文本被按预期拦截也计为场景通过，不代表真实模型回答正确率。", ""]
            if key == "e2e":
                summary += ["| 检查 | 结果 |", "|---|---|"]
                for row in report[key]["cases"]:
                    summary += [f"| {name} | {'通过' if value else '未通过'} |" for name, value in row.get("checks", {}).items()]
                summary += [""]
    calls = report.get("model_calls", {})
    summary += ["## 模型请求与费用", "", f"请求尝试 {calls.get('actual_model_calls', 0)} / 上限 {calls.get('max_model_calls', '未配置')}；校验成功 {calls.get('successful_calls', 0)}，失败 {calls.get('failed_calls', 0)}。", "",
                "实际返回的Token usage：" + json.dumps(calls.get("token_usage"), ensure_ascii=False) + f"；完整：{calls.get('usage_complete', False)}；费用：未估造（null）。", "",
                "物理请求计数包含失败和重试；预算耗尽/配置失败不发送请求。Token 为供应商实际返回部分，缺失不补造；费用为 null。", "",
                "离线 timing 为本机 TestClient/检索；在线 timing 另含供应商请求。P50/P95 为 nearest-rank，不代表生产 SLA。", "",
                "事实/权限/状态检查不是完整语义准确率；manual_review.csv 的语言质量、清晰度、政策解释均待独立人工填写。", "", "## 失败样例", ""]
    for key,row in failures:
        reason = row.get("reason") or row.get("checks") or "正确文档未在 Top-3 命中"
        summary.append(f"- {key}/{row['id']}：{row['input']}；原因/检查：{reason}")
    if not failures:
        summary.append("本轮样例均符合预期；不代表未覆盖场景或线上效果已通过。")
    summary += ["", "## 改进建议", "", "先人工复核歧义标注并补充冻结的独立问题，再按错误类别比较规则、模型分类和检索。不要根据本开发集调参后宣称泛化提升。"]
    (output/"summary.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
    with (output/"manual_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["component", "case_id", "run_id", "response_mode", "response", "review_status",
                                                   "reviewer", "reviewed_at", "tone_1_5", "clarity_1_5", "policy_grounding_1_5", "notes"])
        writer.writeheader()
        for key in ("reply", "e2e"):
            for row in report.get(key, {}).get("cases", []):
                for result in row.get("results", []):
                    values = {"component": key, "case_id": row["id"], "run_id": result["run_id"],
                              "response_mode": ("tool_" + result["tool_calling_trace"].get("status", "unrecorded"))
                                  if result.get("tool_calling_trace", {}).get("enabled") else reply_eval.response_mode(result)[0],
                              "response": result.get("final_response", ""),
                              "review_status": "pending"}
                    writer.writerow({name: csv_safe(value) for name,value in values.items()})


write_reports = write_artifact  # 第一阶段 Python 调用兼容


def main(argv=None):
    parser=argparse.ArgumentParser(description="ServiceFlow 模拟数据评测，离线模式不调用模型 API")
    parser.add_argument("--mode",choices=["offline","live"],default="offline",help="live 显式请求供应商，会消耗额度；未选组件时仍仅 intent")
    parser.add_argument("--output",type=Path,default=ROOT/"reports")
    parser.add_argument("--live-limit",type=int,default=80,help="live 模式最多分类样例数（1..80）")
    parser.add_argument("--components", help="显式选择 intent、reply 或 intent,reply；离线默认两者，live 默认仅 intent")
    parser.add_argument("--reply-limit", type=int, default=6, help="回复场景数量 1..6；一个场景可能含多轮回复")
    parser.add_argument("--max-model-calls", type=int, help="物理请求硬上限（含重试），1..500；live 回复评测必须显式指定")
    parser.add_argument("--check-config", action="store_true", help="只验证配置，不创建客户端、不发送任何模型请求")
    args=parser.parse_args(argv)
    if not 1<=args.live_limit<=80: parser.error("--live-limit 必须位于 1..80")
    if not 1<=args.reply_limit<=6: parser.error("--reply-limit 必须位于 1..6")
    components = args.components.split(",") if args.components else (["intent"] if args.mode == "live" else ["intent", "reply"])
    if any(item not in {"intent", "reply"} for item in components) or len(set(components)) != len(components):
        parser.error("--components 只支持 intent、reply 或 intent,reply，不能重复")
    if args.mode == "live" and "reply" in components and args.max_model_calls is None and not args.check_config:
        parser.error("live 回复评测必须明确 --max-model-calls；不会隐式扩大原 live-limit 的消费范围")
    settings = None
    try:
        ledger = CallLedger(args.max_model_calls if args.max_model_calls is not None else args.live_limit)
        if args.mode == "live" or args.check_config:
            from dotenv import load_dotenv
            load_dotenv(ROOT.parent/".env")
            settings = ModelSettings.read()
    except ValueError as exc:
        parser.error(str(exc))
    if args.check_config:
        print(json.dumps({"configuration": settings.public(), "network_calls": 0}, ensure_ascii=False))
        return 0
    intent_cases=load("intent_cases.jsonl")
    if args.mode=="live":
        with model_calls(ledger), patch.dict(os.environ,{"LLM_INTENT_ENABLED":"true"}):
            intent=intent_eval.evaluate(intent_cases[:args.live_limit],live=True) if "intent" in components else intent_eval.evaluate(intent_cases)
            reply=reply_eval.evaluate(load("reply_cases.jsonl")[:args.reply_limit],live=True) if "reply" in components else {"execution_mode":"not_requested","cases":[],"metrics":{"sample_count":0,"passed":0}}
    else:
        with patch.dict(os.environ,{"LLM_API_KEY":"","LLM_INTENT_ENABLED":"false"}):
            intent=intent_eval.evaluate(intent_cases)
            reply=reply_eval.evaluate(load("reply_cases.jsonl")) if "reply" in components else {"execution_mode":"not_requested","cases":[],"metrics":{"sample_count":0,"passed":0}}
    rag=rag_eval.evaluate(load("rag_cases.jsonl"))
    workflow=workflow_eval.evaluate(load("workflow_cases.jsonl"))
    rag["execution_mode"] = workflow["execution_mode"] = "offline"
    faults=failure_checks.evaluate()
    receipt=receipt_eval.evaluate(load("receipt_cases.jsonl"))
    report={"schema_version":2,"generated_at":datetime.now(timezone.utc).isoformat(),"mode":args.mode,
            "data_provenance":"AI-assisted synthetic development labels; NOT independently human-reviewed; NOT production data",
            "live_components":components if args.mode=="live" else [],
            **fingerprints(), "configuration": settings.public() if settings else None,
            "evaluation_overrides": {"intent_live": args.mode == "live" and "intent" in components,
                                     "reply_eval_intent_live": False, "sdk_hidden_retries": 0},
            "model_calls": ledger.summary(), "intent":intent,"rag":rag,"workflow":workflow,"reply":reply,"faults":faults,"receipt":receipt}
    write_reports(report,args.output.resolve())
    print(json.dumps({"output":str(args.output.resolve()),"intent_accuracy":intent["metrics"]["accuracy"],
                      "workflow_passed":workflow["metrics"]["passed"],"workflow_total":workflow["metrics"]["sample_count"],
                      "reply_passed":reply["metrics"]["passed"], "faults_passed":faults["metrics"]["passed"],
                      "receipt_passed":receipt["metrics"]["passed"],
                      "actual_model_calls":len(ledger.calls)},ensure_ascii=False))
    return 0 if all(report[key]["metrics"]["passed"] == report[key]["metrics"]["sample_count"] for key in ("workflow", "reply", "faults", "receipt")) else 1


if __name__=="__main__":
    raise SystemExit(main())
