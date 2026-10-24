"""NumPy cosine search over a validated local policy index."""
import numpy as np
from .embedding_client import EmbeddingError, normalized_vectors, minimize_query
from .rag_index import query_key


class DenseRetriever:
    def __init__(self, index, chunks, client=None, *, remote_query=False):
        self.index, self.chunks, self.client = index, chunks, client
        self.remote_query = remote_query

    def search(self, query, top_k, ledger):
        cached = self.index.query_vectors.get(query_key(query))
        if cached is not None:
            vector = normalized_vectors([cached], 1, self.index.dimensions)[0]
        elif not self.remote_query or self.client is None:
            raise EmbeddingError("query_not_cached_remote_disabled")
        else:
            vector = self.client.embed([minimize_query(query)], ledger)[0]
            if len(self.index.query_vectors) < 256:
                self.index.query_vectors[query_key(query)] = vector.tolist()
        try:
            sims = self.index.vectors @ vector
            if not np.isfinite(sims).all():
                raise EmbeddingError("similarity_error")
            ranked = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), self.chunks[i].chunk_id))[:top_k]
            return [{**self.chunks[i].record(), "score": round(float(sims[i]), 6), "score_type": "dense_cosine",
                     "dense_rank": rank, "retrieval_mode": "dense"} for rank, i in enumerate(ranked, 1)]
        except (ValueError, TypeError, FloatingPointError):
            raise EmbeddingError("similarity_error") from None
