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
        trace = decision.model_trace if live else {}
        rows.append({"id":case["id"], "case_id":case["id"], "input":case["text"], "gold":case["intent"], "gold_label":case["intent"], "predicted":decision.intent,
                     "passed":decision.intent==case["intent"], "reason":decision.reason,
                     "rule_prediction": baseline.intent, "model_prediction":trace.get("model_prediction"),
                     "final_prediction":decision.intent, "model_used":trace.get("model_used",False),
                     "fallback_used":trace.get("fallback_used",False), "guard_applied":trace.get("guard_applied",False),
                     "error_type":trace.get("error_type"), "actual_model_calls":trace.get("actual_model_calls",0),
                     "call_ids":trace.get("call_ids",[]), "mode":trace.get("mode","rules"),
                     "latency_ms":(time.perf_counter()-started)*1000})
    metrics = classification_metrics([r["gold"] for r in rows],[r["predicted"] for r in rows])
    metrics.update(mode="model_with_rule_fallback" if live else "rules", token_usage=None)
    baseline_metrics = classification_metrics([r["gold"] for r in rows],[r["rule_prediction"] for r in rows])
    raw_rows = [row for row in rows if row["model_prediction"] is not None]
    attempts = sum(row["actual_model_calls"] for row in rows)
    model_success = sum(row["model_used"] for row in rows)
    fallbacks = sum(row["fallback_used"] for row in rows)
    eligible = sum(not row["guard_applied"] for row in rows) if live else 0
    metrics.update(actual_model_calls=attempts, model_success_count=model_success, fallback_count=fallbacks,
                   guard_count=sum(row["guard_applied"] for row in rows), model_eligible_cases=eligible,
                   model_success_rate=model_success/eligible if eligible else None,
                   fallback_rate=fallbacks/eligible if eligible else None)
    return {"metrics":metrics,"rule_baseline":baseline_metrics,
            "raw_model_metrics":classification_metrics([r["gold"] for r in raw_rows],[r["model_prediction"] for r in raw_rows]),
            "raw_model_note":"仅统计实际成功解析的模型输出，不包含 guard、错误与规则回退；与全样本 Accuracy 不可直接比较",
            "execution_mode":"live" if live else "offline","cases":rows}
