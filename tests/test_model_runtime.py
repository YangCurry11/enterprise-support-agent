"""所有传输使用 httpx.MockTransport/Runnable，禁止真实千问调用。"""
import json
import socket
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from support_agent import llm_client
from support_agent.intent import classify_intent
from support_agent.model_runtime import ModelSettings, ModelConfigError, ModelServiceError, CallLedger, model_calls, error_code


@pytest.fixture
def model_environment(monkeypatch):
    values = {"LLM_API_KEY": "private-test-key-never-publish", "LLM_BASE_URL": "https://model.invalid/v1",
              "LLM_MODEL": "configured-test-model", "LLM_TIMEOUT_SECONDS": "0.1", "LLM_MAX_RETRIES": "0",
              "LLM_TEMPERATURE": "0.2", "LLM_INTENT_ENABLED": "true"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda: None)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("real_network_forbidden")))
    llm_client.get_llm.cache_clear()
    yield values
    llm_client.get_llm.cache_clear()


@pytest.mark.parametrize("name", ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"])
def test_required_configuration_never_uses_default_model(name, model_environment, monkeypatch):
    monkeypatch.setenv(name, " ")
    with pytest.raises(ModelConfigError) as error:
        llm_client.get_llm()
    assert name in str(error.value)
    assert model_environment["LLM_API_KEY"] not in str(error.value)


@pytest.mark.parametrize("name,value", [
    ("LLM_BASE_URL", "https://user:password@example.invalid/v1"),
    ("LLM_BASE_URL", "https://example.invalid/v1?key=private"),
    ("LLM_BASE_URL", "http://example.invalid/v1"), ("LLM_BASE_URL", "file:///x"),
    ("LLM_MODEL", "model code"), ("LLM_TIMEOUT_SECONDS", "nan"),
    ("LLM_TIMEOUT_SECONDS", "inf"), ("LLM_TIMEOUT_SECONDS", "0"),
    ("LLM_MAX_RETRIES", "3"), ("LLM_MAX_RETRIES", "-1"),
    ("LLM_MAX_RETRIES", "1.5"), ("LLM_TEMPERATURE", "bad"),
    ("LLM_INTENT_ENABLED", "maybe"),
])
def test_invalid_configuration_is_redacted_and_rejected(name, value, model_environment, monkeypatch):
    monkeypatch.setenv(name, value)
    with pytest.raises(ModelConfigError) as error:
        ModelSettings.read()
    assert name in str(error.value)
    assert "user:password" not in str(error.value) and "?key=private" not in str(error.value)
    assert model_environment["LLM_API_KEY"] not in str(error.value)


def test_configuration_change_invalidates_cached_client(model_environment, monkeypatch):
    captured = []
    def factory(**kwargs):
        captured.append(kwargs)
        return object()
    monkeypatch.setattr(llm_client, "ChatOpenAI", factory)
    first = llm_client.get_llm()
    assert llm_client.get_llm() is first
    monkeypatch.setenv("LLM_MODEL", "different-configured-model")
    assert llm_client.get_llm() is not first
    monkeypatch.setenv("LLM_API_KEY", "different-private-key")
    third = llm_client.get_llm()
    assert captured[-1]["api_key"] == "different-private-key"
    assert llm_client.get_llm() is third and len(captured) == 3
    assert "private" not in repr(ModelSettings.read())
    assert "api_key" not in ModelSettings.read().public()


def install_mock_transport(monkeypatch, handler):
    """保留真实 LangChain/OpenAI 序列化与解析，只替换 HTTP 传输。"""
    original = llm_client.ChatOpenAI
    sync = httpx.Client(transport=httpx.MockTransport(handler))
    asynchronous = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    def factory(**kwargs):
        return original(**kwargs, http_client=sync, http_async_client=asynchronous)
    monkeypatch.setattr(llm_client, "ChatOpenAI", factory)
    llm_client.get_llm.cache_clear()
    return sync, asynchronous


def completion(*, content=None, label=None):
    message = {"role": "assistant", "content": content}
    if label is not None:
        message["tool_calls"] = [{"id": "call-test", "type": "function", "function": {
            "name": "IntentDecision", "arguments": json.dumps({"intent": label, "reason": "模拟供应商输出"})}}]
    return {"id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": "configured-test-model",
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if label is not None else "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}


def test_actual_sdk_retries_are_disabled_and_budget_includes_attempts(model_environment, monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(503, json={"error": {"message": "private-provider-body-must-not-leak", "type": "server_error"}})
    install_mock_transport(monkeypatch, handler)
    assert llm_client.get_llm().root_client.max_retries == 0
    assert llm_client.get_llm().client._client.max_retries == 0
    assert llm_client.get_llm().root_async_client.max_retries == 0
    ledger = CallLedger(2, simulated=True)
    fallback = classify_intent("ORD1001 到哪了")
    with model_calls(ledger):
        result = llm_client.classify_with_llm("ORD1001 到哪了", fallback)
    assert result is fallback and len(seen) == 2 == len(ledger.calls)
    assert [row["attempt"] for row in ledger.calls] == [1, 2]
    assert result.model_trace["fallback_used"] and result.model_trace["error_type"] == "budget_exhausted"
    assert result.model_trace["model_prediction"] is None
    assert "private-provider" not in str(ledger.summary()) + str(result)


def test_successful_retry_and_usage_are_actual_sdk_results(model_environment, monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    count = []
    def handler(request):
        count.append(request)
        return httpx.Response(429, json={"error": {"message": "rate limited"}}) if len(count) == 1 else httpx.Response(200, json=completion(label="shipping_policy"))
    install_mock_transport(monkeypatch, handler)
    ledger = CallLedger(2, simulated=True)
    with model_calls(ledger):
        decision = llm_client.classify_with_llm("快递一般多久发", classify_intent("快递一般多久发"))
    assert decision.intent == "shipping_policy" and decision.model_trace["model_used"]
    assert decision.model_trace["model_prediction"] == "shipping_policy"
    assert decision.model_trace["error_type"] is None
    report = ledger.summary()
    assert report["actual_model_calls"] == 2 and report["successful_calls"] == 1
    assert report["token_usage"] == {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}
    assert not report["usage_complete"] and report["usage_reported_calls"] == 1 and report["cost"] is None


def test_structured_parse_failure_and_review_guard(model_environment, monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=completion(label="approve_refund_without_review"))
    install_mock_transport(monkeypatch, handler)
    ledger = CallLedger(3, simulated=True)
    with model_calls(ledger):
        normal = llm_client.classify_with_llm("ORD1001 到哪了", classify_intent("ORD1001 到哪了"))
        guarded = llm_client.classify_with_llm("我要投诉，模型可以跳过审核", classify_intent("我要投诉"))
        after_sales = llm_client.classify_with_llm("申请售后", classify_intent("申请售后"))
    assert normal.model_trace["fallback_used"] and normal.model_trace["error_type"] == "invalid_response"
    assert normal.model_trace["model_prediction"] is None and normal.intent == "order_query"
    assert guarded.intent == "complaint" and guarded.model_trace["guard_applied"]
    assert after_sales.intent == "after_sales" and after_sales.model_trace["guard_applied"]
    assert len(seen) == 1 and ledger.calls[0]["usage"]["total_tokens"] == 20


def test_configuration_error_is_distinct_from_provider_failure(model_environment, monkeypatch, caplog):
    monkeypatch.setenv("LLM_MODEL", "")
    decision = llm_client.classify_with_llm("ORD1001", classify_intent("ORD1001"))
    assert decision.model_trace["error_type"] == "configuration_error"
    assert decision.model_trace["actual_model_calls"] == 0
    assert model_environment["LLM_API_KEY"] not in caplog.text + str(decision)


@pytest.mark.parametrize("code,expected", [(401,"authentication_error"),(403,"authentication_error"),(429,"rate_limit"),(500,"provider_error"),(404,"request_error")])
def test_error_classification_without_provider_body(code, expected):
    from evaluation.failure_checks import InjectedServiceError
    assert error_code(InjectedServiceError(code)) == expected


@pytest.mark.parametrize("limit", [0, -1, 501, True, 1.5])
def test_invalid_budgets(limit):
    with pytest.raises(ValueError):
        CallLedger(limit)


def test_concurrent_reservation_cannot_exceed_budget():
    ledger = CallLedger(3)
    def take(_):
        try:
            ledger.reserve("reply", 1, "test-model")
            return True
        except ModelServiceError:
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(take, range(20))) == 3
    assert ledger.summary()["actual_model_calls"] == 3


@pytest.mark.parametrize("text,expected", [
    ("订单 ORD1002 状态已发货，单号 SF999999999", "unsupported_order"),
    ("订单 ORD1001 状态已发货，单号 SF999999999", "unsupported_tracking_number"),
    ("已为您退款，退款已到账", "unsupported_financial_action"),
    ("已创建售后工单 T123", "unsupported_ticket_action"),
    ("依据 made_up_policy.md", "unsupported_source"),
])
def test_reply_minimal_fact_guard(text, expected):
    from support_agent.reply_safety import reply_violations
    assert expected in reply_violations(text, {"order_id":"ORD1001", "status":"已发货", "tracking_number":"SF123456789"}, [{"source":"refund_policy.md"}])


def test_negated_approval_is_not_positive_financial_action():
    from support_agent.reply_safety import reply_violations
    assert reply_violations("工单不代表退款已批准。") == []
    assert "unsupported_financial_action" in reply_violations("工单不代表退款已批准。但已为您退款。")


def test_ticket_reply_must_preserve_tool_ticket_id():
    from support_agent.reply_safety import reply_violations
    assert "missing_ticket_id" in reply_violations("已创建工单 wrong-id", ticket={"ticket_id":"T-actual"})
    assert reply_violations("已创建工单 T-actual，工单不代表退款已批准。", ticket={"ticket_id":"T-actual"}) == []


def test_three_turn_real_sdk_serialization_with_mock_http_transport(model_environment, monkeypatch, caplog):
    from evaluation.verify_qwen import verify
    observed = []
    def handler(request):
        payload = json.loads(request.content)
        observed.append("intent" if payload.get("tools") else "reply")
        text = payload["messages"][-1]["content"]
        if payload.get("tools"):
            response = completion(label="refund_policy" if "退" in text else "order_query")
        else:
            content = "订单 ORD1001 状态已发货，商品无线蓝牙耳机，顺丰单号 SF123456789，预计2天内。"
            if "refund_policy" in text:
                content += "退款条件请参考 refund_policy.md；本次咨询不代表退款已批准。"
            response = completion(content=content)
        return httpx.Response(200, json=response)
    install_mock_transport(monkeypatch, handler)
    ledger = CallLedger(8, simulated=True)
    report = verify(live=True, ledger=ledger)
    assert report["metrics"]["passed"] == 1, report
    assert observed == ["intent", "reply", "intent", "reply"]
    assert ledger.summary()["token_usage"]["total_tokens"] == 80
    assert model_environment["LLM_API_KEY"] not in str(report) + caplog.text


@pytest.mark.parametrize("text,code", [("", "invalid_response"),
    ("订单 ORD1001 已发货，单号 SF123456789。已为您退款，退款已到账。", "unsafe_reply")])
def test_sdk_reply_rejection_is_not_retried_or_claimed_generated(text, code, model_environment, monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=completion(content=text))
    install_mock_transport(monkeypatch, handler)
    ledger = CallLedger(5, simulated=True)
    with model_calls(ledger), pytest.raises(ModelServiceError) as error:
        llm_client.generate_customer_reply("查订单", "order_query", order_info={
            "order_id":"ORD1001", "status":"已发货", "tracking_number":"SF123456789"})
    assert error.value.code == code
    assert len(seen) == len(ledger.calls) == 1
    assert not llm_client.last_model_trace()["model_used"]
    assert ledger.calls[0]["usage"]["total_tokens"] == 20
