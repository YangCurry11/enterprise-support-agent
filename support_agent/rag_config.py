"""Server-only retrieval configuration. No chat setting or secret reuse."""
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
from .config import BASE_DIR
from .model_runtime import ModelConfigError, _number


def boolean(name, default=False):
    value = os.getenv(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise ModelConfigError(name + " must be true or false")
    return value == "true"


@dataclass(frozen=True)
class RagSettings:
    mode: str = "tfidf"
    enabled: bool = False
    remote_query: bool = False
    cache_dir: Path = BASE_DIR / ".rag_cache"
    rrf_k: int = 60
    candidates: int = 20
    query_budget: int = 2

    @classmethod
    def read(cls):
        mode = os.getenv("RAG_MODE", "tfidf").lower()
        if mode not in {"tfidf", "dense", "hybrid"}:
            raise ModelConfigError("RAG_MODE must be tfidf, dense or hybrid")
        return cls(mode, boolean("EMBEDDING_ENABLED"), boolean("RAG_REMOTE_QUERY_ENABLED"),
                   Path(os.getenv("RAG_CACHE_DIR", str(BASE_DIR / ".rag_cache"))).resolve(),
                   _number("RAG_RRF_K", 60, 1, 1000, True),
                   _number("RAG_CANDIDATES", 20, 5, 1000, True),
                   _number("RAG_QUERY_MAX_EMBEDDING_CALLS", 2, 1, 20, True))


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str
    base_url: str = field(repr=False)
    dimensions: int
    api_key: str = field(default="", repr=False)
    timeout: float = 20
    max_retries: int = 1

    @classmethod
    def read(cls, *, require_key=False):
        model = os.getenv("EMBEDDING_MODEL", "").strip()
        base = os.getenv("EMBEDDING_BASE_URL", "").strip().rstrip("/")
        key = os.getenv("EMBEDDING_API_KEY", "").strip()
        if not model or len(model) > 160 or any(c.isspace() for c in model):
            raise ModelConfigError("Explicit EMBEDDING_MODEL required; chat model is not reused")
        try:
            url = urlsplit(base)
            valid = url.hostname and url.scheme in {"http", "https"} and not (url.username or url.password or url.query or url.fragment)
            _ = url.port
        except ValueError:
            valid = False
        if not valid or (url.scheme != "https" and url.hostname not in {"127.0.0.1", "localhost", "::1"}):
            raise ModelConfigError("EMBEDDING_BASE_URL must be a safe HTTPS compatible URL")
        if require_key and not key:
            raise ModelConfigError("EMBEDDING_API_KEY required")
        dimensions = _number("EMBEDDING_DIMENSIONS", 0, 1, 8192, True)
        if model == "text-embedding-v4" and dimensions not in {64, 128, 256, 512, 768, 1024, 1536, 2048}:
            raise ModelConfigError("Unsupported text-embedding-v4 dimensions; verify provider documentation")
        return cls(model, base, dimensions, key,
                   _number("EMBEDDING_TIMEOUT_SECONDS", 20, .1, 120),
                   _number("EMBEDDING_MAX_RETRIES", 1, 0, 2, True))

    def identity(self):
        return {"model": self.model, "dimensions": self.dimensions,
                "endpoint_hash": hashlib.sha256(self.base_url.encode()).hexdigest()}

    def public(self):
        return {"model": self.model, "dimensions": self.dimensions,
                "endpoint_host": urlsplit(self.base_url).hostname, "key_configured": bool(self.api_key),
                "timeout_seconds": self.timeout, "max_retries": self.max_retries}
