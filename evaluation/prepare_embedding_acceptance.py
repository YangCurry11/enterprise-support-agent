"""Local-only acceptance inventory/report reader. No live execution option or SDK client."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

from support_agent.config import BASE_DIR
from support_agent.embedding_client import minimize_query
from support_agent.model_runtime import ModelConfigError
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import EmbeddingSettings, RagSettings
from support_agent.rag_index import SPLIT_VERSION, atomic_json, digest, query_key
from .rag_comparison import validate_cases

DATASETS = ("rag_cases.jsonl", "rag_hard_cases.jsonl")
# Official public synchronous input prices, reviewed 2026-10-24, CNY/1M.
# Not an account quote, free quota assumption, Batch API price or live price fetch.
PRICES = {"cn-beijing": 0.5, "ap-southeast-1": 0.514}
SENSITIVE = {
    "email": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "identity_number": r"(?<!\d)\d{17}[\dXx](?!\d)",
    "business_identifier": r"(?<![A-Za-z0-9])(?:ORD\d+|TKT[A-Za-z0-9]+|U\d+|(?:SF|JD|YT|ZT|ST)\d+)(?![A-Za-z0-9])",
    "credential_like": r"\bsk-[A-Za-z0-9_-]{8,}|-----BEGIN .*PRIVATE KEY-----",
}


def endpoint_region(base_url):
    """Recognize documented hosts only; never echo an arbitrary URL/WorkspaceId."""
    try:
        url = urlsplit(base_url)
        if (url.scheme != "https" or url.port not in (None, 443) or url.username or url.password
                or url.query or url.fragment or url.path.rstrip("/") != "/compatible-mode/v1"):
            return None
        host = url.hostname or ""
        legacy = {"dashscope.aliyuncs.com": "cn-beijing", "dashscope-intl.aliyuncs.com": "ap-southeast-1"}
        if host in legacy:
            return legacy[host]
        match = re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(cn-beijing|ap-southeast-1)\.maas\.aliyuncs\.com", host)
        return match.group(1) if match else None
    except ValueError:
        return None


def configuration_check():
    result = {"api_key_configured": bool(os.getenv("EMBEDDING_API_KEY", "").strip()),
              "embedding_configuration_valid": False, "candidate_model_matches": False,
              "endpoint_region": None, "key_region_match": "requires_console_confirmation"}
    try:
        cfg = EmbeddingSettings.read(require_key=False)
        result.update(embedding_configuration_valid=True, candidate_model_matches=cfg.model == "text-embedding-v4",
                      dimensions=cfg.dimensions, timeout_seconds=cfg.timeout, max_retries=cfg.max_retries,
                      endpoint_region=endpoint_region(cfg.base_url))
    except ModelConfigError:
        pass  # Never serialize environment values or arbitrary exception text.
    try:
        rag = RagSettings.read()
        result.update(rag_configuration_valid=True, rag_mode=rag.mode, embedding_enabled=rag.enabled,
                      remote_query_enabled=rag.remote_query)
    except ModelConfigError:
        result["rag_configuration_valid"] = False
    return result


def text_inventory(texts):
    return {"text_count": len(texts), "characters": sum(map(len, texts)),
            "utf8_bytes": sum(len(t.encode("utf-8")) for t in texts),
            "max_characters": max(map(len, texts), default=0),
            "max_utf8_bytes": max((len(t.encode("utf-8")) for t in texts), default=0)}


def inventory():
    kb = PolicyKnowledgeBase(settings=RagSettings())  # Force TF-IDF, even with a live .env.
    root = BASE_DIR / "evaluation" / "datasets"
    datasets = {name: [json.loads(line) for line in (root / name).read_text(encoding="utf-8").splitlines()
                       if line.strip()] for name in DATASETS}
    for cases in datasets.values():
        validate_cases(cases, kb)
    all_cases = [c for cases in datasets.values() for c in cases]
    queries = {query_key(c["query"]): minimize_query(c["query"]) for c in all_cases}
    chunks = [c.text for c in kb.chunks]
    requests = math.ceil(len(chunks) / 10) + math.ceil(len(queries) / 10)
    # Locations only, not matched sensitive data or full query text in the preflight report.
    payloads = [(c.chunk_id, c.text) for c in kb.chunks] + list(queries.items())
    findings = [{"payload_id": key, "categories": [name for name, pattern in SENSITIVE.items()
                  if re.search(pattern, text, re.I)]} for key, text in payloads]
    findings = [f for f in findings if f["categories"]]
    policies = {c.source: c.document_hash for c in kb.chunks}
    dataset_hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in DATASETS}
    char_proxy = sum(map(len, chunks)) + sum(map(len, queries.values()))
    byte_proxy = sum(len(t.encode("utf-8")) for _, t in payloads)
    return {
        "split_version": SPLIT_VERSION, "corpus_hash": digest([c.record() for c in kb.chunks]),
        "policy_hashes": policies, "dataset_hashes": dataset_hashes,
        "dataset_counts": {name: {"total": len(cases), "positive": sum(bool(c.get("gold_source")) for c in cases),
                                 "no_support": sum(not c.get("gold_source") for c in cases)} for name, cases in datasets.items()},
        "chunks": text_inventory(chunks), "minimized_unique_queries": text_inventory(list(queries.values())),
        "query_count_before_dedup": len(all_cases),
        "changed_queries_by_minimization": sum(c["query"] != minimize_query(c["query"]) for c in all_cases),
        "request_plan": {"document_batches": math.ceil(len(chunks) / 10), "query_batches": math.ceil(len(queries) / 10),
                         "cold_build_no_retries": requests, "warm_complete_cache": 0,
                         "unbatched_queries_if_not_prebuilt": len(queries),
                         "potential_attempts_if_budget_expanded": {str(r): requests * (1 + r) for r in range(3)},
                         "recommended_total_attempt_limit": requests, "recommended_max_retries": 0},
        "token_and_cost_planning": {
            "actual_tokens": None, "tokenizer_verified": False,
            "character_proxy_not_actual_tokens": char_proxy, "utf8_byte_proxy_not_token_cap": byte_proxy,
            "price_cny_per_million_input_tokens": PRICES,
            "proxy_cost_cny_by_region": {region: {"character_proxy": char_proxy * price / 1e6,
                                                  "byte_proxy": byte_proxy * price / 1e6} for region, price in PRICES.items()},
            "documented_service_limit_tokens_for_attempt_cap": requests * 10 * 8192,
            "service_limit_cost_cny_by_region": {region: requests * 10 * 8192 * price / 1e6 for region, price in PRICES.items()},
            "runtime_token_hard_cap_implemented": False,
            "warning": "Proxies are not provider tokens; service-limit bound is conditional, not an account-level spending cap."},
        "data_export_review": {"pattern_findings": findings, "pattern_scan_is_complete_pii_detection": False,
                               "owner_authorization": "pending", "scope": "policy chunks + minimized fixed eval queries only"},
        "no_support_review_template": [{"case_id": c.get("case_id") or c.get("id"),
                                        "existing_gold_has_support": False, "reviewer_confirmed_gold": None,
                                        "per_mode_evidence_review": {mode: {"supports_question": None, "chunk_ids": [],
                                                                                  "rationale": None} for mode in ("tfidf", "dense", "hybrid")},
                                        "reviewer": None, "reviewed_at": None}
                                       for c in all_cases if not c.get("gold_source")],
        "ndcg_at_3": None, "ndcg_status": "pending independent relevance judgments; unjudged is not irrelevant",
    }


def summarize_recorded(build, comparison, region):
    """Read real artifacts only; cumulative per-search ledgers must NOT be summed."""
    if build.get("mode") != "live" or build.get("source") != "live_dense" or build.get("status") not in {"built", "reused"}:
        raise ValueError("a successful real build report is required, not Mock")
    if comparison.get("embedding_source") not in {"real_cached_dense", "live_dense"}:
        raise ValueError("a real comparison report is required, not Mock")
    current = inventory()
    if (build.get("index_metadata", {}).get("corpus_hash") != current["corpus_hash"]
            or comparison.get("policy_hashes") != current["policy_hashes"]
            or any(comparison.get("datasets", {}).get(k) != v for k, v in current["dataset_hashes"].items())):
        raise ValueError("report fingerprints do not match the current corpus/datasets")
    counts = []
    for report in (build, comparison):
        cfg = report.get("configuration", {})
        if cfg.get("model") != "text-embedding-v4" or endpoint_region("https://" + (cfg.get("endpoint_host") or "") + "/compatible-mode/v1") != region:
            raise ValueError("recorded model/region does not match the reviewed price basis")
        counts.append(report["embedding_calls"])
    if build["configuration"].get("dimensions") != comparison["configuration"].get("dimensions"):
        raise ValueError("recorded dimensions differ")
    calls = [row for ledger in counts for row in ledger["calls"]]
    if any(ledger["actual_embedding_calls"] != len(ledger["calls"]) for ledger in counts):
        raise ValueError("inconsistent recorded attempt count")
    usages = [row["usage"] for row in calls if row.get("usage") is not None]
    tokens = sum(u["input_tokens"] for u in usages) if usages else None
    modes = {}
    for dataset, results in comparison["datasets_results"].items():
        for mode, result in results.items():
            rows = result["cases"]
            applicable = [r for r in rows if mode in {"dense", "hybrid"}]
            eligible = [r for r in applicable if r["retrieval"]["actual_mode"] == mode
                        and not r["retrieval"].get("fallback_reason")]
            hits = sum(r["retrieval"]["embedding_attempts_this_search"] == 0 for r in eligible)
            modes[dataset + "/" + mode] = {"recorded_metrics": result["metrics"],
                "query_cache_hit_rate": hits / len(applicable) if applicable else None,
                "cache_hit_count": hits if applicable else None, "cache_lookup_count": len(applicable) if applicable else None,
                "cache_measurement_scope": "successful Dense/Hybrid + zero attempts; sequential shared cache, not independent cold timing",
                "support_evidence_verdict": "pending independent manual review", "ndcg_at_3": None}
    return {"recorded_embedding_attempts": len(calls), "reported_input_tokens": tokens,
            "usage_complete": all(row.get("usage") is not None for row in calls),
            "estimated_cost_from_reported_usage_cny": tokens * PRICES[region] / 1e6 if tokens is not None else None,
            "cost_is_final_bill": False, "unreported_attempt_usage_count": len(calls) - len(usages),
            "warning": "Missing usage is unknown, not zero. Provider bill is authoritative; cost excludes other jobs/chat calls.",
            "modes": modes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--comparison-report", type=Path)
    parser.add_argument("--price-region", choices=tuple(PRICES))
    args = parser.parse_args(argv)
    if any((args.build_report, args.comparison_report, args.price_region)) and not all((args.build_report, args.comparison_report, args.price_region)):
        parser.error("recorded summary requires build-report, comparison-report and price-region together")
    output = args.output or BASE_DIR / "evaluation" / ("reports-rag-preparation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    if output.exists():
        parser.error("output exists; choose a new directory")
    try:
        result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                  "preparation_embedding_api_calls": 0, "actual_calls_authorized": False,
                  "ready_to_call": False, "configuration": configuration_check(), "inventory": inventory()}
        if args.build_report:
            if args.build_report.resolve() == args.comparison_report.resolve():
                raise ValueError("build and comparison reports must be distinct")
            result["recorded_results"] = summarize_recorded(json.loads(args.build_report.read_text(encoding="utf-8")),
                json.loads(args.comparison_report.read_text(encoding="utf-8")), args.price_region)
        output.mkdir(parents=True, exist_ok=False)
        atomic_json(output / "latest.json", result)
        print(json.dumps({"output": str(output), "configuration": result["configuration"],
                          "preparation_embedding_api_calls": 0, "ready_to_call": False}, ensure_ascii=False))
        return 0  # Successful inventory, NOT permission to call.
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("local preparation failed; inspect input files/configuration without publishing secrets")


if __name__ == "__main__":
    raise SystemExit(main())
