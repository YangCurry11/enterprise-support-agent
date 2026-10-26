import time
from .metrics import retrieval_metrics


def evaluate(cases):
    from support_agent.rag import PolicyKnowledgeBase
    from support_agent.rag_config import RagSettings
    kb = PolicyKnowledgeBase(settings=RagSettings())  # Historical baseline always offline TF-IDF.
    rows = []
    for case in cases:
        document = kb.policy_dir / case["gold_source"]
        if not document.is_file() or case["gold_evidence"] not in document.read_text(encoding="utf-8"):
            raise ValueError(f"无法追溯检索标注：{case['id']}")
        started = time.perf_counter()
        hits = kb.search(case["query"],top_k=5)
        latency = (time.perf_counter()-started)*1000
        sources = [hit["source"] for hit in hits]
        rows.append({"id":case["id"],"input":case["query"],"gold_sources":[case["gold_source"]],
                     "retrieved_sources":sources,"latency_ms":latency,"passed":case["gold_source"] in sources[:3],
                     "gold_evidence":case["gold_evidence"], "expected_topic":case["expected_topic"]})
    return {"metrics":retrieval_metrics(rows),"cases":rows}
