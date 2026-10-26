"""Versioned atomic JSON cache; no pickle, no remote work on cache misses."""
from dataclasses import asdict
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from .embedding_client import EmbeddingError, normalized_vectors, minimize_query

SPLIT_VERSION = "markdown-v1-unchanged-600-500"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def manifest(chunks, settings):
    records = [asdict(chunk) for chunk in chunks]
    return {"schema_version": 1, "split_version": SPLIT_VERSION, **settings.identity(),
            "corpus_hash": digest(records), "chunk_ids": [c.chunk_id for c in chunks]}


def query_key(query):
    return digest(minimize_query(query))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as handle:
            name = handle.name
            json.dump(data, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()  # Only our own incomplete temp, never a prior index.


class DenseIndex:
    def __init__(self, chunks, settings, vectors, *, provenance="live", query_vectors=None):
        self.metadata = manifest(chunks, settings)
        self.vectors = normalized_vectors(vectors, len(chunks), settings.dimensions)
        self.provenance = provenance
        if query_vectors is not None and (not isinstance(query_vectors, dict) or len(query_vectors) > 256
                or any(not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) for key in query_vectors)):
            raise EmbeddingError("index_invalid")
        self.query_vectors = {} if query_vectors is None else dict(query_vectors)
        self.dimensions = settings.dimensions
        for value in self.query_vectors.values():
            normalized_vectors([value], 1, settings.dimensions)

    def save(self, path):
        atomic_json(path, {"metadata": self.metadata, "provenance": self.provenance,
                           "vectors": self.vectors.tolist(), "query_vectors": self.query_vectors})

    @classmethod
    def load(cls, path, chunks, settings):
        try:
            path = Path(path)
            if not path.is_file():
                raise EmbeddingError("index_missing")
            if path.stat().st_size > 32 * 1024 * 1024:
                raise EmbeddingError("index_invalid")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw["metadata"] != manifest(chunks, settings):
                raise EmbeddingError("index_stale")
            if raw["provenance"] != "live":
                raise EmbeddingError("index_not_real")
            return cls(chunks, settings, raw["vectors"], provenance=raw["provenance"], query_vectors=raw.get("query_vectors"))
        except EmbeddingError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            raise EmbeddingError("index_invalid") from None


def build_index(chunks, settings, client, ledger, queries=()):
    vectors = []
    for start in range(0, len(chunks), 10):
        vectors.extend(client.embed([c.text for c in chunks[start:start+10]], ledger).tolist())
    index = DenseIndex(chunks, settings, vectors)
    # Optional query cache enables genuinely offline REAL-cached comparisons.
    unique = {query_key(q): minimize_query(q) for q in queries}
    keys = sorted(unique)
    for start in range(0, len(keys), 10):
        batch = keys[start:start+10]
        matrix = client.embed([unique[key] for key in batch], ledger)
        index.query_vectors.update({key: value.tolist() for key, value in zip(batch, matrix)})
    return index
