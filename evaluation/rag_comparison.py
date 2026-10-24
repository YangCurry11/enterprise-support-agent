"""Frozen-source document/chunk retrieval metrics, not answer accuracy."""
import time
from collections import Counter
from .evaluators.metrics import retrieval_metrics, timing_metrics


def validate_cases(cases, kb):
    for case in cases:
        source, evidence = case.get("gold_source"), case.get("gold_evidence")
        if not source:
            if evidence or case.get("gold_chunk_id"):
                raise ValueError("negative case must not have positive evidence")
            continue
        # Gold is evidence-grounded BEFORE any prediction, not inferred from returned hits.
        candidates = [c for c in kb.chunks if c.source == source and evidence and evidence in c.text]
        if not candidates or (case.get("gold_chunk_id") and case["gold_chunk_id"] not in {c.chunk_id for c in candidates}):
            raise ValueError("untraceable gold evidence: " + (case.get("case_id") or case["id"]))


def evaluate(cases, kb, source_label, ledger):
    validate_cases(cases, kb)
    rows = []
    for case in cases:
        expected = {c.chunk_id for c in kb.chunks if c.source == case.get("gold_source")
                    and case.get("gold_evidence") and case["gold_evidence"] in c.text}
        if case.get("gold_chunk_id"):
            expected = {case["gold_chunk_id"]}
        started = time.perf_counter()
        result = kb.search_with_trace(case["query"], 5, ledger=ledger)
        hits, trace = result["data"], result["retrieval"]
        positive = bool(case.get("gold_source"))
        evidence_rank = next((i for i, h in enumerate(hits, 1) if h["chunk_id"] in expected), None)
        row = {"id": case.get("case_id") or case["id"], "query": case["query"],
               "gold_sources": [case["gold_source"]] if positive else [], "gold_evidence": case.get("gold_evidence"),
               "expected_chunk_ids": sorted(expected), "retrieved_sources": [h["source"] for h in hits],
               "hits": hits, "retrieval": trace, "evidence_rank": evidence_rank,
               "passed": (case["gold_source"] in [h["source"] for h in hits[:3]] and evidence_rank is not None and evidence_rank <= 3) if positive else not hits,
               "latency_ms": (time.perf_counter() - started) * 1000,
               "review_status": "pending", "source_label": source_label}
        rows.append(row)
    positives = [r for r in rows if r["gold_sources"]]
    negatives = [r for r in rows if not r["gold_sources"]]
    metrics = retrieval_metrics(positives)
    metrics["timing"] = timing_metrics([row["latency_ms"] for row in rows])
    metrics["timing_scope"] = "all queries incl no-support; sequential in-process, shared query vectors"
    metrics["positive_count"] = len(positives)
    metrics["negative_count"] = len(negatives)
    metrics["no_support_correct"] = sum(not r["hits"] for r in negatives)
    metrics["negative_return_rate"] = sum(bool(r["hits"]) for r in negatives)/len(negatives) if negatives else None
    for k in (1, 3, 5):
        metrics[f"evidence_hit_at_{k}"] = sum(r["evidence_rank"] is not None and r["evidence_rank"] <= k for r in positives)/len(positives) if positives else None
    metrics["evidence_mrr"] = sum(1/r["evidence_rank"] if r["evidence_rank"] else 0 for r in positives)/len(positives) if positives else None
    metrics["fallback_count"] = sum(bool(r["retrieval"]["fallback_reason"]) for r in rows)
    metrics["actual_mode_counts"] = dict(Counter(r["retrieval"]["actual_mode"] for r in rows))
    return {"configured_mode": kb.settings.mode, "source_label": source_label, "metrics": metrics, "cases": rows,
            "failures": [r["id"] for r in rows if not r["passed"]]}
