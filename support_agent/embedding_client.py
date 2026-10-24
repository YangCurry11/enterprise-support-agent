"""Explicit, independently budgeted OpenAI-compatible embeddings, never chat calls."""
from dataclasses import dataclass, field
import re
import threading
import time
import numpy as np
from .model_runtime import error_code


class EmbeddingError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("Embedding unavailable: " + code)


def minimize_query(text):
    # Best-effort minimization, NOT a general PII detector. Never send chat history.
    text = re.sub(r"(?<![A-Za-z0-9])(?:ORD\d+|TKT[A-Za-z0-9]+|U\d+|(?:SF|JD|YT|ZT|ST)\d+)(?![A-Za-z0-9])", " [业务编号] ", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " [邮箱] ", text)
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", " [手机号] ", text)
    text = re.sub(r"(?<!\d)\d{6,}[\dXx]?(?!\d)", " [长编号] ", text)
    return text[:1000]


def normalized_vectors(values, rows, dimensions):
    try:
        raw = np.asarray(values)
        if raw.dtype.kind not in "iuf" or raw.shape != (rows, dimensions):
            raise EmbeddingError("dimension_mismatch")
        matrix = raw.astype(np.float64)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if not np.isfinite(matrix).all() or not np.isfinite(norms).all() or (norms <= 0).any():
            raise EmbeddingError("invalid_vector")
        return matrix / norms
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingError("invalid_vector") from None


@dataclass
class EmbeddingLedger:
    limit: int
    calls: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if type(self.limit) is not int or not 1 <= self.limit <= 500:
            raise ValueError("embedding call budget must be 1..500")

    def reserve(self, model, attempt):
        with self.lock:
            if len(self.calls) >= self.limit:
                raise EmbeddingError("budget_exhausted")
            row = {"model": model, "attempt": attempt, "success": False,
                   "error_type": None, "usage": None, "latency_ms": 0}
            self.calls.append(row)
            return row

    def summary(self):
        rows = [dict(row) for row in self.calls]
        usages = [row["usage"] for row in rows if row["usage"] is not None]
        return {"max_embedding_calls": self.limit, "actual_embedding_calls": len(rows), "calls": rows,
                "token_usage": {k: sum(u[k] for u in usages) for k in ("input_tokens", "total_tokens")} if usages else None,
                "usage_reported_calls": len(usages), "usage_complete": bool(rows) and len(usages) == len(rows),
                "cost": None, "count_definition": "SDK invoke attempts incl. retries, not billing confirmation"}


class EmbeddingClient:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client  # Lazy: constructing a KB does not even construct an SDK client.

    def embed(self, texts, ledger):
        if not texts or len(texts) > 10 or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise EmbeddingError("invalid_input")
        if self.client is None:
            if not self.settings.api_key:
                raise EmbeddingError("configuration_error")
            from openai import OpenAI
            # Own SDK transports must close on success, error AND budget rejection.
            # Injected clients remain owned by their caller (e.g. MockTransport tests).
            with OpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url,
                        timeout=self.settings.timeout, max_retries=0) as client:
                return self._request(texts, ledger, client)
        return self._request(texts, ledger, self.client)

    def _request(self, texts, ledger, client):
        for attempt in range(1, self.settings.max_retries + 2):
            row = ledger.reserve(self.settings.model, attempt)
            started = time.perf_counter()
            try:
                result = client.embeddings.create(model=self.settings.model, input=texts,
                    dimensions=self.settings.dimensions, encoding_format="float")
                usage = getattr(result, "usage", None)
                prompt, total = getattr(usage, "prompt_tokens", None), getattr(usage, "total_tokens", None)
                # Bailian v4 documents input-only billing and may omit prompt_tokens.
                # Use provider-reported total, never a character/token estimate. Do not
                # extrapolate this contract to unknown models or malformed usage.
                if prompt is None and self.settings.model == "text-embedding-v4":
                    prompt = total
                if type(prompt) is int and type(total) is int and 0 <= prompt <= total:
                    row["usage"] = {"input_tokens": prompt, "total_tokens": total}
                data = sorted(result.data, key=lambda item: item.index)
                if [item.index for item in data] != list(range(len(texts))):
                    raise EmbeddingError("invalid_response")
                matrix = normalized_vectors([item.embedding for item in data], len(texts), self.settings.dimensions)
                row["success"] = True
                return matrix
            except Exception as exc:
                code = exc.code if isinstance(exc, EmbeddingError) else "invalid_response" if isinstance(exc, (ValueError, TypeError, AttributeError)) else error_code(exc)
                row["error_type"] = code
                if attempt > self.settings.max_retries or code not in {"timeout", "connection_error", "rate_limit", "provider_error"}:
                    raise EmbeddingError(code) from None
                time.sleep(min(.1 * attempt, .2))
            finally:
                row["latency_ms"] = (time.perf_counter() - started) * 1000
