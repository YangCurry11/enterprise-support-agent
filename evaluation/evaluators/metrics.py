"""纯函数指标。分位数采用 nearest-rank：排序后第 ceil(p*n) 个。"""
import math


LABELS = ["order_query", "refund_policy", "shipping_policy", "after_sales", "complaint", "human_escalation", "chit_chat", "unknown"]


def classification_metrics(gold, predicted, labels=LABELS):
    if len(gold) != len(predicted):
        raise ValueError("标签和预测数量不一致")
    matrix = [[0 for _ in labels] for _ in labels]
    for actual, prediction in zip(gold, predicted):
        matrix[labels.index(actual)][labels.index(prediction)] += 1
    classes = {}
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        support = sum(matrix[i])
        predicted_count = sum(row[i] for row in matrix)
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
        classes[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
    return {"sample_count": len(gold), "accuracy": sum(a == b for a,b in zip(gold,predicted))/len(gold) if gold else None,
            "macro_f1": sum(row["f1"] for row in classes.values())/len(labels),
            "per_class": classes, "labels": labels, "confusion_matrix": matrix}


def percentile(values, p):
    if not 0 < p <= 1:
        raise ValueError("分位点必须位于 (0,1]")
    return sorted(values)[max(0, math.ceil(p*len(values))-1)] if values else None


def timing_metrics(values):
    return {"sample_count": len(values), "mean_ms": sum(values)/len(values) if values else None,
            "p50_ms": percentile(values,.5), "p95_ms": percentile(values,.95), "quantile_method": "nearest-rank"}


def retrieval_metrics(rows):
    n = len(rows)
    scores = {f"recall_at_{k}": 0.0 for k in (1,3,5)}
    reciprocal = 0
    for row in rows:
        gold = set(row["gold_sources"])
        for k in (1,3,5):
            scores[f"recall_at_{k}"] += len(gold & set(row["retrieved_sources"][:k])) / len(gold)
        rank = next((i+1 for i,source in enumerate(row["retrieved_sources"]) if source in gold), None)
        reciprocal += 1/rank if rank else 0
    return {"sample_count":n, **{key:value/n if n else None for key,value in scores.items()},
            "mrr": reciprocal/n if n else None, "relevance_unit":"source document, not chunk relevance",
            "timing": timing_metrics([row["latency_ms"] for row in rows])}
