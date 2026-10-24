"""Three-mode retrieval comparison. Offline defaults to clearly labeled lexical MOCK."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import uuid
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import RagSettings, EmbeddingSettings, boolean
from support_agent.embedding_client import EmbeddingClient, EmbeddingLedger, EmbeddingError
from support_agent.model_runtime import ModelConfigError
from support_agent.rag_index import DenseIndex, build_index, atomic_json
from support_agent.dense_retriever import DenseRetriever
from .mock_embedding import MockEmbedding
from .rag_comparison import evaluate, validate_cases
from .run_evaluation import load, fingerprints, csv_safe


def new_output(kind):
    return Path(__file__).parent / ("reports-rag-" + kind + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])


def write_comparison(report, output):
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "latest.json", report)
    lines = ["# Phase 3A 实际检索对照", "", "模拟开发标注，pending human review；不是答案准确率。",
             "Mock只验证算法与工程，不是Embedding模型语义效果；fallback不得当Dense成功。", "",
             "| 集合 / 模式 | 来源 | R@1 | R@3 | R@5 | MRR | 证据@3 | mean ms | P50 | P95 | 回退 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    with (output / "details.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dataset", "mode", "id", "passed", "actual_mode", "fallback_reason", "detail"])
        for dataset, modes in report["datasets_results"].items():
            for mode, result in modes.items():
                m = result["metrics"]
                values = [m[k] for k in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr", "evidence_hit_at_3")]
                values += [m["timing"][k] for k in ("mean_ms", "p50_ms", "p95_ms")]
                lines.append("| " + " | ".join([dataset + " / " + mode, result["source_label"]] + [f"{v:.4f}" if v is not None else "n/a" for v in values] + [str(m["fallback_count"])]) + " |")
                for row in result["cases"]:
                    writer.writerow([csv_safe(v) for v in (dataset, mode, row["id"], row["passed"], row["retrieval"]["actual_mode"], row["retrieval"]["fallback_reason"], json.dumps(row, ensure_ascii=False))])
    lines += ["", "## 失败与无依据样例（保留，不删）", ""]
    for dataset, modes in report["datasets_results"].items():
        for mode, result in modes.items():
            lines.append(f"- {dataset}/{mode}: " + (", ".join(result["failures"]) or "本集合已覆盖检查通过"))
            lines.append(f"  无依据问题 {result['metrics']['negative_count']} 条，负例空召回数 {result['metrics']['no_support_correct']} 条（仅候选诊断，不是政策证据判定）。正样本Recall不包含负样本；是否存在可支持回答的证据须单独人工复核。")
    lines += ["", "三种模式共享相同语料、原切分、问题与gold；Dense/Hybrid共享查询向量缓存，顺序执行，计时不用于声称公平速度提升或生产SLA。", "",
              "融合分不是置信度。没有输出答案事实正确率。人工复核尚未完成。费用为null；usage只使用供应商实际返回。"]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--source", choices=["mock", "cache", "live"])
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--max-embedding-calls", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    source = args.source or ("live" if args.mode == "live" else "mock")
    if (source == "live") != (args.mode == "live") or (args.mode == "live" and (not args.allow_remote or args.max_embedding_calls is None)):
        parser.error("live requires --mode live --source live --allow-remote --max-embedding-calls N; offline cannot use live")
    output = args.output or new_output("compare-" + args.mode + "-" + source)
    if output.exists():
        parser.error("output already exists; choose a NEW directory to preserve earlier reports")
    try:
        ledger = EmbeddingLedger(args.max_embedding_calls if args.max_embedding_calls is not None else 1)
        baseline = PolicyKnowledgeBase(settings=RagSettings())
        datasets = {"historical20": load("rag_cases.jsonl"), "hard16": load("rag_hard_cases.jsonl")}
        for cases in datasets.values():
            validate_cases(cases, baseline)
        if source == "mock":
            settings = EmbeddingSettings("MOCK-lexical-hash-v1", "https://mock.invalid/v1", 128)
            client = MockEmbedding()
            index = build_index(baseline.chunks, settings, client, ledger)
            index.provenance = "mock"
            rag_settings = RagSettings(enabled=True, remote_query=True)
        else:
            if source == "live":
                from dotenv import load_dotenv
                load_dotenv()
                if not boolean("EMBEDDING_ENABLED"):
                    raise ModelConfigError("EMBEDDING_ENABLED=true is required for remote operations")
            settings = EmbeddingSettings.read(require_key=source == "live")
            rag_settings = replace(RagSettings.read(), enabled=True, remote_query=source == "live")
            index = DenseIndex.load(rag_settings.cache_dir / "policy_index.json", baseline.chunks, settings)
            client = EmbeddingClient(settings) if source == "live" else None
        retriever = DenseRetriever(index, baseline.chunks, client, remote_query=rag_settings.remote_query)
        kbs = {"tfidf": baseline, **{mode: PolicyKnowledgeBase(settings=replace(rag_settings, mode=mode),
               embedding_settings=settings, dense=retriever) for mode in ("dense", "hybrid")}}
        label = {"mock": "mock_dense", "cache": "real_cached_dense", "live": "live_dense"}[source]
        results = {name: {mode: evaluate(cases, kb, "tfidf_baseline" if mode == "tfidf" else label, ledger)
                          for mode, kb in kbs.items()} for name, cases in datasets.items()}
        report = {"schema_version": 1, "mode": args.mode, "embedding_source": label,
                  "generated_at": datetime.now(timezone.utc).isoformat(), **fingerprints(),
                  "configuration": settings.public(), "embedding_calls": ledger.summary(), "datasets_results": results,
                  "annotation_status": "pending human review", "answers_evaluated": False}
        write_comparison(report, output)
        if source == "live":
            index.save(rag_settings.cache_dir / "policy_index.json")
        print(json.dumps({"output": str(output), "source": label, "actual_embedding_calls": len(ledger.calls)}, ensure_ascii=False))
        # Retrieval misses are MEASUREMENTS, not reasons to delete cases or fudge gold.
        return 1 if any(r["metrics"]["fallback_count"] for modes in results.values() for r in modes.values()) else 0
    except (EmbeddingError, ModelConfigError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
