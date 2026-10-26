"""Read-only real-report audit and pending human evidence sheet. NEVER calls models."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re

from support_agent.config import BASE_DIR
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import EmbeddingSettings, RagSettings
from support_agent.rag_index import atomic_json, manifest
from .compare_rag import new_output
from .evaluators.metrics import retrieval_metrics
from .prepare_embedding_acceptance import endpoint_region, inventory, summarize_recorded
from .rag_comparison import validate_cases
from .run_evaluation import load

MODES = ("tfidf", "dense", "hybrid")
DATASETS = {"historical20": "rag_cases.jsonl", "hard16": "rag_hard_cases.jsonl"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_cached(report, kb, datasets):
    require(report["mode"] == "offline" and report["embedding_source"] == "real_cached_dense", "not a real cached report")
    ledger = report["embedding_calls"]
    require(ledger["actual_embedding_calls"] == 0 and ledger["calls"] == [], "cache report contains requests")
    expected_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (BASE_DIR / "evaluation" / "datasets").glob("*.jsonl")}
    require(report["datasets"] == expected_hashes, "dataset fingerprints changed")
    require(report["policy_hashes"] == {c.source: c.document_hash for c in kb.chunks}, "policy fingerprints changed")
    require(set(report["datasets_results"]) == set(datasets), "wrong dataset set")
    chunks = {c.chunk_id: c.record() for c in kb.chunks}
    for name, cases in datasets.items():
        validate_cases(cases, kb)
        require(set(report["datasets_results"][name]) == set(MODES), "missing/extra retrieval mode")
        for mode, result in report["datasets_results"][name].items():
            rows = result["cases"]
            require([r["id"] for r in rows] == [c.get("case_id", c.get("id")) for c in cases], "missing, duplicate or reordered cases")
            require(result["configured_mode"] == mode, "configured mode mismatch")
            require(result["source_label"] == ("tfidf_baseline" if mode == "tfidf" else "real_cached_dense"), "row source mismatch")
            for case, row in zip(cases, rows):
                gold = [case["gold_source"]] if case.get("gold_source") else []
                ids = {c.chunk_id for c in kb.chunks if c.source in gold and case.get("gold_evidence")
                       and case["gold_evidence"] in c.text}
                if case.get("gold_chunk_id"):
                    ids = {case["gold_chunk_id"]}
                require(row["query"] == case["query"] and row["gold_sources"] == gold
                        and row["gold_evidence"] == case.get("gold_evidence")
                        and row["expected_chunk_ids"] == sorted(ids), "query/gold changed")
                require(row["source_label"] == result["source_label"], "per-case source mismatch")
                trace = row["retrieval"]
                require(trace["configured_mode"] == mode and trace["actual_mode"] == mode
                        and trace["fallback_reason"] is None, "retrieval fell back or mode changed")
                require(trace["embedding_attempts_this_search"] == 0
                        and trace["embedding_calls"]["actual_embedding_calls"] == 0
                        and trace["embedding_calls"]["calls"] == [], "per-query report contains requests")
                if mode != "tfidf":
                    require(trace["embedding_model"] == report["configuration"]["model"], "trace model changed")
                hits = row["hits"]
                require(len(hits) <= 5 and len({h["chunk_id"] for h in hits}) == len(hits), "invalid Top-K")
                for rank, hit in enumerate(hits, 1):
                    canonical = chunks.get(hit["chunk_id"])
                    require(canonical is not None and all(hit[k] == v for k, v in canonical.items()), "untraceable chunk content")
                    require(type(hit["score"]) in (int, float) and math.isfinite(hit["score"]), "nonfinite score")
                    require(hit["score_type"] == {"tfidf": "tfidf_cosine", "dense": "dense_cosine", "hybrid": "rrf"}[mode]
                            and hit["retrieval_mode"] == mode, "wrong score semantics")
                    require(hit[{"tfidf": "tfidf_rank", "dense": "dense_rank", "hybrid": "fusion_rank"}[mode]] == rank, "rank mismatch")
                require(row["retrieved_sources"] == [h["source"] for h in hits], "source list mismatch")
                evidence_rank = next((i for i, h in enumerate(hits, 1) if h["chunk_id"] in ids), None)
                require(row["evidence_rank"] == evidence_rank, "evidence rank mismatch")
                passed = (case["gold_source"] in row["retrieved_sources"][:3] and evidence_rank is not None
                          and evidence_rank <= 3) if gold else not hits
                require(row["passed"] == passed, "diagnostic passed flag mismatch")
            positive = [r for r in rows if r["gold_sources"]]
            negative = [r for r in rows if not r["gold_sources"]]
            calculated = {k: v for k, v in retrieval_metrics(positive).items() if k != "timing"}
            calculated.update(positive_count=len(positive), negative_count=len(negative), fallback_count=0,
                              no_support_correct=sum(not r["hits"] for r in negative),
                              negative_return_rate=sum(bool(r["hits"]) for r in negative) / len(negative) if negative else None)
            for k in (1, 3, 5):
                calculated[f"evidence_hit_at_{k}"] = sum(r["evidence_rank"] is not None and r["evidence_rank"] <= k
                                                         for r in positive) / len(positive) if positive else None
            calculated["evidence_mrr"] = sum(1 / r["evidence_rank"] if r["evidence_rank"] else 0 for r in positive) / len(positive) if positive else None
            for key, expected in calculated.items():
                actual = result["metrics"][key]
                require(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12)
                        if type(expected) is float else actual == expected, "metric mismatch: " + key)


def audit(build, first, repeat, stored_summary):
    kb = PolicyKnowledgeBase(settings=RagSettings())
    datasets = {name: load(file) for name, file in DATASETS.items()}
    cfg = build["configuration"]
    require(cfg["model"] == "text-embedding-v4" and cfg["dimensions"] in {64, 128, 256, 512, 768, 1024, 1536, 2048}, "wrong model/dimensions")
    require(cfg == first["configuration"] == repeat["configuration"], "report configurations differ")
    region = endpoint_region("https://" + cfg["endpoint_host"] + "/compatible-mode/v1")
    require(region is not None, "unrecognized endpoint region")
    settings = EmbeddingSettings(cfg["model"], "https://" + cfg["endpoint_host"] + "/compatible-mode/v1", cfg["dimensions"])
    require(build["index_metadata"] == manifest(kb.chunks, settings), "index manifest mismatch")
    plan = inventory()
    require(build["status"] == "built" and build["chunk_count"] == len(kb.chunks)
            and build["query_count_requested"] == plan["query_count_before_dedup"], "incomplete build")
    ledger = build["embedding_calls"]
    require(type(ledger["actual_embedding_calls"]) is int and ledger["actual_embedding_calls"] == len(ledger["calls"])
            == plan["request_plan"]["cold_build_no_retries"] <= ledger["max_embedding_calls"], "build attempt count mismatch")
    for call in ledger["calls"]:
        require(call["model"] == cfg["model"] and call["success"] is True and call["error_type"] is None, "unsuccessful build attempt")
        require(call["attempt"] == 1, "unexpected retry")
        usage = call["usage"]
        require(isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "total_tokens"))
                and usage["input_tokens"] == usage["total_tokens"], "invalid/missing input-only usage")
    token_usage = {k: sum(c["usage"][k] for c in ledger["calls"]) for k in ("input_tokens", "total_tokens")}
    require(ledger["usage_complete"] is True and ledger["usage_reported_calls"] == len(ledger["calls"])
            and ledger["token_usage"] == token_usage, "ledger usage aggregate mismatch")
    validate_cached(first, kb, datasets)
    validate_cached(repeat, kb, datasets)
    require(first["source_hashes"] == repeat["source_hashes"], "recorded source fingerprints differ")
    counted, candidates = 0, 0
    for name in datasets:
        for mode in MODES:
            for left, right in zip(first["datasets_results"][name][mode]["cases"], repeat["datasets_results"][name][mode]["cases"]):
                fields = ("chunk_id", "score", "score_type", "tfidf_rank", "dense_rank", "fusion_rank")
                signature = lambda row: [tuple(h.get(k) for k in fields) for h in row["hits"]]
                require(signature(left) == signature(right), "repeat Top-K/rank/score mismatch: " + left["id"])
                counted += 1
                candidates += len(left["hits"])
    totals = summarize_recorded(build, first, region)
    require(stored_summary["recorded_results"] == totals and stored_summary["inventory"] == plan, "stored acceptance summary mismatch")
    return {"audit_model_api_calls": 0, "recorded_results": totals, "model": cfg["model"], "dimensions": cfg["dimensions"],
            "endpoint_region": region, "corpus_hash": plan["corpus_hash"], "dataset_hashes": plan["dataset_hashes"],
            "compared_case_mode_rows": counted, "compared_candidate_rows": candidates, "top_k_reproducible": True,
            "review_status": "pending independent human review", "automatic_safe_refusal_verified": False,
            "ndcg_at_3": None, "ndcg_reason": "no independently reviewed exhaustive relevance judgments"}


def md(value):
    text = html.escape(str(value))
    return re.sub(r"([\\`*_[\]{}()|])", r"\\\1", text).replace("\n", "<br>")


def evidence_sheet(report):
    lines = ["# Phase 3A 待独立人工核查证据表", "", "真实缓存来源：real_cached_dense。本表是机械整理，不是已完成人工复核。",
             "保留原36题（20+13正例+3无依据）；已有gold仅作定位，命中gold不等于独立证据充分性判断。",
             "每题每模式的人工支持判定、复核人和时间均待填写。无依据题不得用候选是否为空代替证据判断。", ""]
    for name, modes in report["datasets_results"].items():
        for i, base in enumerate(modes["tfidf"]["cases"]):
            lines += [f"## {md(base['id'])} / {name}", "", "问题：" + md(base["query"]),
                      "", "原gold：" + md(base["gold_evidence"] or "无支持证据（原标注，待独立复核）"),
                      "", "人工总体结论：待填写；复核人：待填写；时间：待填写。", ""]
            for mode in MODES:
                row = modes[mode]["cases"][i]
                lines += [f"### {mode} / 原gold证据排名：{row['evidence_rank'] or '未命中'}", "",
                          "| Top-K序位 | source / chunk_id | 分数及类型 | TF-IDF / Dense / RRF排名 | 完整片段 | 原gold命中（机械） | 独立人工支持判定 / 理由 |",
                          "|---|---|---|---|---|---|---|"]
                for rank, hit in enumerate(row["hits"], 1):
                    values = [rank, hit["source"] + " / " + hit["chunk_id"], str(hit["score"]) + " / " + hit["score_type"],
                              " / ".join(str(hit.get(k, "—")) for k in ("tfidf_rank", "dense_rank", "fusion_rank")), hit["text"],
                              hit["chunk_id"] in row["expected_chunk_ids"], "待填写"]
                    lines.append("| " + " | ".join(md(v) for v in values) + " |")
                lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "first", "repeat", "summary"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or new_output("acceptance-audit")
    if output.exists():
        parser.error("output exists; choose a new private report directory")
    try:
        paths = [getattr(args, name) for name in ("build", "first", "repeat", "summary")]
        require(len({p.resolve() for p in paths}) == 4, "input reports must be distinct")
        raw = [p.read_bytes() for p in paths]
        reports = [json.loads(b) for b in raw]
        result = audit(*reports)
        result["input_sha256"] = {name: hashlib.sha256(b).hexdigest() for name, b in zip(("build", "first", "repeat", "summary"), raw)}
        sheet = evidence_sheet(reports[1])
        output.mkdir(parents=True, exist_ok=False)
        atomic_json(output / "latest.json", result)
        (output / "evidence_review.md").write_text(sheet, encoding="utf-8")
        print(json.dumps({"output": str(output), "compared_rows": result["compared_case_mode_rows"],
                          "candidate_rows": result["compared_candidate_rows"], "audit_model_api_calls": 0,
                          "human_review": "pending", "top_k_reproducible": True}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        parser.error("local real-report audit failed; no model invoked; inspect report structure and provenance privately")


if __name__ == "__main__":
    raise SystemExit(main())
