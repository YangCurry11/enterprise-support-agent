import time
from .metrics import classification_metrics, LABELS


def evaluate(cases, live=False):
    from support_agent.intent import classify_intent
    from support_agent.llm_client import classify_with_llm
    rows = []
    for case in cases:
        if case["intent"] not in LABELS:
            raise ValueError("不支持的标注意图")
        started = time.perf_counter()
        baseline = classify_intent(case["text"])
        decision = classify_with_llm(case["text"], baseline) if live else baseline
        rows.append({"id":case["id"], "input":case["text"], "gold":case["intent"], "predicted":decision.intent,
                     "passed":decision.intent==case["intent"], "reason":decision.reason,
                     "model_used":decision.reason.startswith("结构化模型分类"),
                     "latency_ms":(time.perf_counter()-started)*1000})
    metrics = classification_metrics([r["gold"] for r in rows],[r["predicted"] for r in rows])
    metrics.update(mode="model_with_rule_fallback" if live else "rules", token_usage=None)
    return {"metrics":metrics,"cases":rows}
