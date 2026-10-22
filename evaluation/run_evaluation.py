"""python -m evaluation.run_evaluation；默认离线，报告只含模拟数据。"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
from .evaluators import intent_eval, rag_eval, workflow_eval

ROOT = Path(__file__).resolve().parent


def load(name):
    return [json.loads(line) for line in (ROOT/"datasets"/name).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_reports(report, output):
    output.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    # 同目录临时文件 + 原子替换，API 不会读到半份报告。
    temporary = output/"latest.json.tmp"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output/"latest.json")
    with (output/"details.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["component","id","input","passed","latency_ms","detail"])
        writer.writeheader()
        for component in ("intent","rag","workflow"):
            for row in report[component]["cases"]:
                writer.writerow({"component":component,"id":row["id"],"input":row["input"],"passed":row["passed"],
                                 "latency_ms":row["latency_ms"],"detail":json.dumps(row,ensure_ascii=False)})
    i,r,w = (report[key]["metrics"] for key in ("intent","rag","workflow"))
    failures = [(key,row) for key in ("intent","rag","workflow") for row in report[key]["cases"] if not row["passed"]]
    summary = ["# Agent 实际评测报告", "", f"生成时间：{report['generated_at']}；模式：{report['mode']}。", "",
               "数据为 AI 辅助编写的模拟开发标注，尚未经独立人工复核，不是实际客户数据或独立测试集。", "",
               f"意图：{i['sample_count']} 条，Accuracy={i['accuracy']:.4f}，Macro-F1={i['macro_f1']:.4f}。", "",
               f"RAG：{r['sample_count']} 条，文档级 Recall@1/3/5={r['recall_at_1']:.4f}/{r['recall_at_3']:.4f}/{r['recall_at_5']:.4f}，MRR={r['mrr']:.4f}。", "",
               f"工作流：{w['passed']}/{w['sample_count']} 场景通过；这是预期行为符合率，不是所有 run 都完成或真实问题解决率。", "",
               "耗时是本机 TestClient 集成请求和本地检索计时，不含公网、供应商排队或真实用户流量。P50/P95 使用 nearest-rank。", "",
               "各类别 Precision/Recall/F1、混淆矩阵、工具成功率、失败次数、回退次数和明细见 latest.json 与 details.csv。", "",
               "未取得实际 Token usage 时报告为 null，不估造 Token 数或 API 成本。", "", "## 失败样例", ""]
    for key,row in failures:
        reason = row.get("reason") or row.get("checks") or "正确文档未在 Top-3 命中"
        summary.append(f"- {key}/{row['id']}：{row['input']}；原因/检查：{reason}")
    if not failures:
        summary.append("本轮样例均符合预期；不代表未覆盖场景或线上效果已通过。")
    summary += ["", "## 改进建议", "", "先人工复核歧义标注并补充冻结的独立问题，再按错误类别比较规则、模型分类和检索。不要根据本开发集调参后宣称泛化提升。"]
    (output/"summary.md").write_text("\n".join(summary)+"\n",encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser(description="ServiceFlow 模拟数据评测，离线模式不调用模型 API")
    parser.add_argument("--mode",choices=["offline","live"],default="offline",help="live 显式启用真实模型意图分类，会消耗额度")
    parser.add_argument("--output",type=Path,default=ROOT/"reports")
    parser.add_argument("--live-limit",type=int,default=80,help="live 模式最多分类样例数（1..80）")
    args=parser.parse_args(argv)
    if not 1<=args.live_limit<=80: parser.error("--live-limit 必须位于 1..80")
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent/".env")
    intent_cases=load("intent_cases.jsonl")
    if args.mode=="live":
        if not all(os.getenv(name) for name in ("LLM_API_KEY","LLM_BASE_URL","LLM_MODEL")):
            parser.error("live 模式需要明确配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL")
        with patch.dict(os.environ,{"LLM_INTENT_ENABLED":"true"}):
            intent=intent_eval.evaluate(intent_cases[:args.live_limit],live=True)
    else:
        with patch.dict(os.environ,{"LLM_API_KEY":"","LLM_INTENT_ENABLED":"false"}):
            intent=intent_eval.evaluate(intent_cases)
    rag=rag_eval.evaluate(load("rag_cases.jsonl"))
    workflow=workflow_eval.evaluate(load("workflow_cases.jsonl"))
    report={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"mode":args.mode,
            "data_provenance":"AI-assisted synthetic development labels; NOT independently human-reviewed; NOT production data",
            "live_components":["intent"] if args.mode=="live" else [],
            "datasets":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"datasets").glob("*.jsonl"))},
            "source_hashes":{name:hashlib.sha256((ROOT.parent/"support_agent"/name).read_bytes()).hexdigest() for name in ("intent.py","rag.py","workflow.py","runtime.py","conversations.py","chat_context.py","agents.py","llm_client.py","scoped_tools.py")},
            "policy_hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT.parent/"data"/"policies").glob("*.md"))},
            "intent":intent,"rag":rag,"workflow":workflow}
    write_reports(report,args.output.resolve())
    print(json.dumps({"output":str(args.output.resolve()),"intent_accuracy":intent["metrics"]["accuracy"],
                      "workflow_passed":workflow["metrics"]["passed"],"workflow_total":workflow["metrics"]["sample_count"]},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
