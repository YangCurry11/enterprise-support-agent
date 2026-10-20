"""Release contract checks: no real model requests and no runtime data writes."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError


def test_exported_openapi_matches_current_application():
    from support_agent.app import app
    source = Path(__file__).resolve().parents[1] / "api" / "openapi_tool_for_dify.yaml"
    exported = json.loads(source.read_text(encoding="utf-8"))
    # The portable export adds an explicit local development server; schemas,
    # operations and security declarations must still match FastAPI exactly.
    assert exported.pop("servers") == [{"url": "http://127.0.0.1:8000"}]
    assert exported == app.openapi()
    assert "post" not in exported["paths"]["/tickets"]


def test_legacy_http_entrypoint_is_same_application():
    from support_agent.app import app
    from support_agent.mock_api import app as compatibility_app
    assert compatibility_app is app


def test_llm_configuration_is_read_without_network(monkeypatch):
    from support_agent import llm_client
    captured = {}
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_API_KEY", "unit-test-placeholder")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model-snapshot")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(llm_client, "ChatOpenAI", fake_client)
    llm_client.get_llm.cache_clear()
    try:
        first = llm_client.get_llm()
        assert llm_client.get_llm() is first
        assert captured == {
            "model": "test-model-snapshot", "api_key": "unit-test-placeholder",
            "base_url": "https://example.invalid/v1", "temperature": 0.1,
            "timeout": 7.0, "max_retries": 1,
        }
    finally:
        llm_client.get_llm.cache_clear()


def test_model_classifier_error_preserves_rule_fallback(monkeypatch):
    from support_agent import llm_client
    from support_agent.intent import IntentResult
    fallback = IntentResult("order_query", "ORD1001", 1.0, "rule")
    monkeypatch.setenv("LLM_INTENT_ENABLED", "true")
    monkeypatch.setattr(llm_client, "is_llm_enabled", lambda: True)
    def unavailable():
        raise TimeoutError("simulated model outage")
    monkeypatch.setattr(llm_client, "get_llm", unavailable)
    assert llm_client.classify_with_llm("订单状态", fallback) is fallback


def test_model_intent_schema_rejects_unknown_actions():
    from support_agent.llm_client import IntentDecision
    with pytest.raises(ValidationError):
        IntentDecision(intent="approve_refund_and_skip_review", reason="untrusted")
