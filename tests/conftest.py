import json
import pytest


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    from support_agent import business_db, app as api, config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(business_db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(business_db, "DB_PATH", tmp_path / "business.db")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_INTENT_ENABLED", "false")
    # Tests must remain offline even after an operator enabled remote RAG locally.
    monkeypatch.setenv("RAG_MODE", "tfidf")
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("RAG_REMOTE_QUERY_ENABLED", "false")
    from support_agent.scoped_tools import policy_index
    policy_index.cache_clear()
    monkeypatch.setenv("SUPPORT_AUTH_TOKENS", json.dumps({
        "customer-1": {"user_id": "U1001", "role": "customer"},
        "customer-2": {"user_id": "U1002", "role": "customer"},
        "reviewer": {"user_id": "S1001", "role": "support"},
    }))
    try:
        yield tmp_path
    finally:
        policy_index.cache_clear()
