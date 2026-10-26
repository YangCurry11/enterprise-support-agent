"""Reciprocal rank fusion: ranks, NOT incomparable similarity scores."""


class HybridRetriever:
    def __init__(self, rrf_k=60):
        if type(rrf_k) is not int or rrf_k < 1:
            raise ValueError("rrf_k must be a positive integer")
        self.rrf_k = rrf_k

    def search(self, sparse, dense, top_k):
        merged = {}
        for name, hits in (("tfidf", sparse), ("dense", dense)):
            seen = set()
            for rank, hit in enumerate(hits, 1):
                key = hit["chunk_id"]
                if key in seen:
                    continue
                seen.add(key)
                item = merged.setdefault(key, {**hit, "score": 0.0, "tfidf_rank": None, "dense_rank": None})
                item[name + "_rank"] = rank
                item["score"] += 1 / (self.rrf_k + rank)
        ranked = sorted(merged.values(), key=lambda hit: (-hit["score"], hit["chunk_id"]))[:top_k]
        return [{**hit, "score_type": "rrf", "retrieval_mode": "hybrid", "fusion_rank": rank}
                for rank, hit in enumerate(ranked, 1)]
