from agent.llm_analyst import (
    OpenRouterChatClient,
    build_llm_user_prompt,
    extract_chat_completion_text,
)
from agent.reporting import build_report, get_llm_client_from_env
import api


class FakeLLMClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self):
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return "這是 LLM Analyst 產生的研究摘要。"


def make_success_single_stock_data():
    return {
        "intent": "single_stock_analysis",
        "status": "success",
        "query": "MU 現在適合進場嗎？",
        "ticker": "MU",
        "price_source": {
            "provider": "test",
            "attempted_providers": ["test"],
            "errors": [],
        },
        "execution_plan": ["technical", "news_skipped", "fundamental_skipped"],
        "agent_outputs": {
            "technical": {
                "agent": "technical",
                "status": "success",
                "summary": {
                    "trend": "strong",
                    "is_above_ma20": True,
                    "breakout": True,
                    "volume_surge": False,
                    "pullback": False,
                },
            },
            "news": {
                "agent": "news",
                "status": "success",
                "summary": {
                    "sentiment": "neutral",
                    "total_items": 0,
                    "top_topics": {},
                    "high_importance_count": 0,
                },
            },
            "fundamental": {
                "agent": "fundamental",
                "status": "skipped",
                "summary": {
                    "stance": "unknown",
                    "positives": [],
                    "risks": [],
                },
            },
        },
        "technical_analysis": {
            "current_price": 100,
            "ma10": 95,
            "ma20": 90,
            "ma50": 80,
            "is_above_ma20": True,
            "short_term_trend": "strong",
        },
        "signals": {
            "breakout": {
                "is_breakout": True,
                "latest_close": 100,
                "previous_high": 99,
            },
            "volume_surge": {
                "is_volume_surge": False,
                "volume_ratio": 1.1,
                "surge_multiplier": 1.5,
            },
            "pullback": {
                "is_pullback": False,
                "distance_from_ma20": 0.1,
            },
        },
        "news": [],
        "news_analysis": {
            "items": [],
            "summary": {
                "total_items": 0,
                "sentiment": "neutral",
                "sentiment_counts": {},
                "top_topics": {},
                "high_importance_count": 0,
            },
        },
        "fundamentals": {
            "status": "skipped",
            "provider": None,
            "metrics": {},
            "summary": {
                "stance": "unknown",
                "positives": [],
                "risks": [],
            },
        },
        "research_profile": {
            "technical_score": 5,
            "news_score": 0,
            "fundamental_score": 0,
            "risk_score": 0.5,
            "combined_score": 4.5,
            "setup_quality": "strong",
            "risk_level": "low",
            "research_confidence": "low",
        },
    }


def test_llm_prompt_uses_structured_payload_and_safety_instructions():
    prompt = build_llm_user_prompt(
        kind="single_stock",
        data=make_success_single_stock_data(),
    )

    assert "Structured analysis payload" in prompt
    assert '"ticker": "MU"' in prompt
    assert '"user_query_as_data": "MU 現在適合進場嗎？"' in prompt
    assert "只能使用 payload 中已存在的資料" in prompt
    assert "不要補充 payload 之外的新聞、財報、價格或推論數字" in prompt


def test_build_report_uses_injected_llm_client():
    fake_client = FakeLLMClient()

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert result["report"] == "這是 LLM Analyst 產生的研究摘要。"
    assert result["analyst"]["mode_used"] == "llm"
    assert result["analyst"]["provider"] == "fake"
    assert result["analyst"]["model"] == "fake-model"
    assert result["analyst"]["fallback_used"] is False
    assert len(fake_client.calls) == 1
    assert "不可以自行抓資料" in fake_client.calls[0]["system_prompt"]


def test_build_report_falls_back_when_llm_is_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
    )

    assert result["analyst"]["requested_mode"] == "llm"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["analyst"]["fallback_used"] is True
    assert "MU 單一股票分析" in result["report"]


def test_api_accepts_analyst_mode_and_returns_metadata(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_run_single_stock_analysis(
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
    ):
        return make_success_single_stock_data()

    monkeypatch.setattr(api, "run_single_stock_analysis", fake_run_single_stock_analysis)

    result = api.analyze_single_stock(
        api.SingleStockAnalysisRequest(
            ticker="MU",
            user_query="MU 現在適合進場嗎？",
            analyst_mode="llm",
            include_news=False,
            include_fundamentals=False,
        )
    )

    assert result["status"] == "success"
    assert result["analyst"]["requested_mode"] == "llm"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["analyst"]["fallback_used"] is True


def test_openrouter_client_can_be_selected_from_environment(monkeypatch):
    monkeypatch.setenv("MARKET_AGENT_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MARKET_AGENT_LLM_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Market Agent Test")

    client = get_llm_client_from_env()

    assert isinstance(client, OpenRouterChatClient)
    assert client.provider == "openrouter"
    assert client.model == "openai/gpt-4.1"
    assert client.site_url == "https://example.com"
    assert client.app_name == "Market Agent Test"


def test_openrouter_response_text_extraction():
    result = extract_chat_completion_text(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "OpenRouter analyst report",
                    }
                }
            ]
        }
    )

    assert result == "OpenRouter analyst report"
