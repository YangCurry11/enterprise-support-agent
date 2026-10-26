"""Explicit policy-only index builder. No application startup invokes this command."""
import argparse
from pathlib import Path
import json
from support_agent.rag import PolicyKnowledgeBase
from support_agent.rag_config import RagSettings, EmbeddingSettings, boolean
from support_agent.embedding_client import EmbeddingClient, EmbeddingLedger, EmbeddingError
from support_agent.rag_index import DenseIndex, build_index, query_key, atomic_json
from support_agent.model_runtime import ModelConfigError
from .mock_embedding import MockEmbedding
from .compare_rag import new_output
from .run_evaluation import load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--max-embedding-calls", type=int)
    parser.add_argument("--include-eval-queries", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "live" and (not args.allow_remote or args.max_embedding_calls is None):
        parser.error("live requires --allow-remote --max-embedding-calls N (exports simulated policy text)")
    output = args.output or new_output("build-" + args.mode)
    if output.exists():
        parser.error("output exists; use a new directory")
    try:
        ledger = EmbeddingLedger(args.max_embedding_calls if args.max_embedding_calls is not None else 1)
        kb = PolicyKnowledgeBase(settings=RagSettings())
        queries = [c["query"] for name in ("rag_cases.jsonl", "rag_hard_cases.jsonl") for c in load(name)] if args.include_eval_queries else []
        if args.mode == "live":
            from dotenv import load_dotenv
            load_dotenv()
            if not boolean("EMBEDDING_ENABLED"):
                raise ModelConfigError("EMBEDDING_ENABLED=true required")
            settings = EmbeddingSettings.read(require_key=True)
            target = RagSettings.read().cache_dir / "policy_index.json"
            client = EmbeddingClient(settings)
        else:
            settings = EmbeddingSettings("MOCK-lexical-hash-v1", "https://mock.invalid/v1", 128)
            target = output / "mock_index.json"  # Never write a fake production policy_index.
            client = MockEmbedding()
        output.mkdir(parents=True, exist_ok=False)
        status, error = "built", None
        try:
            index = None
            if target.exists() and not args.rebuild:
                index = DenseIndex.load(target, kb.chunks, settings)
                if any(query_key(q) not in index.query_vectors for q in queries):
                    raise EmbeddingError("query_cache_incomplete_use_rebuild")
                status = "reused"
            if index is None:
                index = build_index(kb.chunks, settings, client, ledger, queries)
                index.provenance = "live" if args.mode == "live" else "mock"
                index.save(target)
        except (EmbeddingError, OSError) as exc:
            status, error = "failed", exc.code if isinstance(exc, EmbeddingError) else "cache_write_error"
        report = {"mode": args.mode, "source": "live_dense" if args.mode == "live" else "mock_dense",
                  "status": status, "error_type": error, "configuration": settings.public(),
                  "embedding_calls": ledger.summary(), "chunk_count": len(kb.chunks), "query_count_requested": len(queries),
                  "index_metadata": index.metadata if status != "failed" else None}
        atomic_json(output / "latest.json", report)
        print(json.dumps({"output": str(output), "status": status, "error_type": error, "actual_embedding_calls": len(ledger.calls)}, ensure_ascii=False))
        return 1 if error else 0
    except (ModelConfigError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
