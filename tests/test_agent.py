from support_agent.intent import classify_intent, INTENT_ORDER, INTENT_REFUND, extract_order_id


def test_extract_order_id():
    assert extract_order_id("我的订单 ORD1001 到哪了") == "ORD1001"


def test_intent_order():
    result = classify_intent("我的订单 ORD1001 到哪了")
    assert result.intent == INTENT_ORDER
    assert result.order_id == "ORD1001"


def test_intent_refund():
    result = classify_intent("我买了10天还能退吗")
    assert result.intent == INTENT_REFUND


def test_order_number_does_not_override_refund_intent():
    assert classify_intent("ORD1001 我想退货").intent == INTENT_REFUND


def test_shipping_policy_is_reachable():
    assert classify_intent("你们的发货时效规定是什么").intent == "shipping_policy"
