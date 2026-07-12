import json

from agent.hybrid_router import route_market_query


class FakeRouterClient:
    provider = "openrouter"
    model = "test-router"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def generate(self, system_prompt, user_prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps(self.result, ensure_ascii=False)


def test_clear_ticker_question_stays_rule_based():
    client = FakeRouterClient(error=AssertionError("LLM must not run"))
    result = route_market_query("MU 現在適合進場嗎", llm_client=client)
    assert result["intent"] == "single_stock_analysis"
    assert result["ticker"] == "MU"
    assert result["router_used"] == "rule_based"
    assert client.calls == 0


def test_low_confidence_natural_question_uses_llm_router():
    client = FakeRouterClient(
        {
            "intent": "single_stock_analysis",
            "ticker": "NVDA",
            "tickers": ["NVDA"],
            "theme": None,
            "strategy": None,
            "question_type": "entry_or_research",
            "confidence": 0.92,
            "reason": "The company name refers to NVDA.",
        }
    )
    result = route_market_query("可以研究一下輝達現在的狀況嗎", llm_client=client)
    assert result["ticker"] == "NVDA"
    assert result["router_used"] == "llm"
    assert result["llm_used"] is True
    assert client.calls == 1


def test_llm_router_can_resolve_natural_backtest_strategy():
    client = FakeRouterClient(
        {
            "intent": "backtest_query",
            "ticker": "MU",
            "tickers": ["MU"],
            "theme": None,
            "strategy": "volume_surge",
            "question_type": "entry_or_research",
            "confidence": 0.9,
            "reason": "The user asks for historical volume-surge performance.",
        }
    )
    result = route_market_query("美光成交量突然增加時，過去通常表現如何", llm_client=client)
    assert result["intent"] == "backtest_query"
    assert result["strategy"] == "volume_surge"


def test_invalid_llm_response_falls_back_to_rule_router():
    client = FakeRouterClient({"intent": "make_trade", "confidence": 1})
    result = route_market_query("幫我看看這家公司最近值不值得研究", llm_client=client)
    assert result["router_used"] == "rule_based_fallback"
    assert result["fallback_used"] is True
    assert result["intent"] == "unknown"


def test_router_error_falls_back_without_breaking_request():
    client = FakeRouterClient(error=RuntimeError("temporary provider error"))
    result = route_market_query("最近的狀況值得注意嗎", llm_client=client)
    assert result["router_used"] == "rule_based_fallback"
    assert "temporary provider error" in result["fallback_reason"]
