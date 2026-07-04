from agent.llm_analyst import (
    OpenRouterChatClient,
    build_llm_payload,
    build_llm_user_prompt,
    extract_chat_completion_text,
)
from agent.report_context import build_single_stock_report_context
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
        return "LLM Analyst test report."


class ExitSectionLLMClient(FakeLLMClient):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return "\n".join(
            [
                "研究摘要",
                "Entry question report.",
                "",
                "持有風險 / 出場觀察",
                "- This section should not appear for entry questions.",
                "",
                "風險提醒",
                "- Test risk note.",
            ]
        )


def make_success_single_stock_data():
    return {
        "intent": "single_stock_analysis",
        "status": "success",
        "query": "MU now suitable for entry?",
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
        "exit_signal": {
            "status": "success",
            "exit_signal": "watch",
            "weakening_signal_20d": "low_to_medium",
            "email_alert_eligible": False,
            "reason": "Trend is still mostly stable but momentum is weakening.",
            "reasons": ["MACD histogram is weakening."],
            "action_note": "Watch MA20 and MACD/RSI before reducing.",
        },
        "data_freshness": {
            "overall": "warning",
            "warnings": [
                {
                    "source": "ml_training_data",
                    "status": "warning",
                    "message": "ML training dataset is older than 7 days.",
                }
            ],
        },
    }


def test_llm_prompt_uses_structured_payload_and_safety_instructions():
    prompt = build_llm_user_prompt(
        kind="single_stock",
        data=make_success_single_stock_data(),
    )

    assert "Structured analysis payload" in prompt
    assert '"ticker": "MU"' in prompt
    assert '"user_query_as_data": "MU now suitable for entry?"' in prompt
    assert '"data_freshness"' in prompt
    assert '"exit_signal"' not in prompt
    assert '"weakening_signal_20d": "low_to_medium"' not in prompt
    assert "ML training dataset is older than 7 days." in prompt


def test_single_stock_report_context_reads_wrapped_agent_outputs():
    data = make_success_single_stock_data()
    news_events_summary = {
        "status": "success",
        "total_events": 2,
        "overall_sentiment": "positive",
    }
    ml_research = {"status": "success", "targets": {}}
    data["agent_outputs"]["news"] = {
        "agent": "news",
        "status": "success",
        "summary": {"sentiment": "positive"},
        "payload": {"news_events_summary": news_events_summary},
        "warnings": [],
        "errors": [],
        "metadata": {},
        "fallback_used": False,
    }
    data["agent_outputs"]["ml_research"] = {
        "agent": "ml_research",
        "status": "success",
        "summary": {},
        "payload": ml_research,
        "warnings": [],
        "errors": [],
        "metadata": {},
        "fallback_used": False,
    }
    data.pop("ml_research", None)

    context = build_single_stock_report_context(data)

    assert context["news_events_summary"] == news_events_summary
    assert context["ml_research"] == ml_research
    assert context["ml_reference_trust"]["status"] == "reduced_trust"
    assert context["agent_summaries"]["news"] == {"sentiment": "positive"}


def test_single_stock_llm_payload_uses_report_context():
    data = make_success_single_stock_data()
    data["agent_outputs"]["evidence"] = {
        "agent": "evidence",
        "status": "success",
        "summary": {"evidence_level": "medium"},
    }

    payload = build_llm_payload("single_stock", data)

    assert payload["kind"] == "single_stock"
    assert payload["ticker"] == data["ticker"]
    assert payload["question_type"] == "entry_or_research"
    assert payload["news_summary"] == data["news_analysis"]["summary"]
    assert payload["fundamental_summary"] == data["fundamentals"]["summary"]
    assert "ml_reference_trust" in payload
    assert payload["agent_summaries"]["evidence"] == {"evidence_level": "medium"}


def test_single_stock_llm_payload_marks_holding_exit_question():
    data = make_success_single_stock_data()
    data["query"] = "MU 如果我已經持有，現在要不要減碼"

    payload = build_llm_payload("single_stock", data)

    assert payload["question_type"] == "holding_exit"
    assert payload["exit_signal"]["exit_signal"] == "watch"


def test_build_report_uses_injected_llm_client():
    fake_client = FakeLLMClient()

    result = build_report(
        kind="single_stock",
        data={**make_success_single_stock_data(), "query": "MU should I reduce my position?"},
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert "LLM Analyst" in result["report"]
    assert "持有風險 / 出場觀察" in result["report"]
    assert result["analyst"]["mode_used"] == "llm"
    assert result["analyst"]["provider"] == "fake"
    assert result["analyst"]["model"] == "fake-model"
    assert result["analyst"]["fallback_used"] is False
    assert len(fake_client.calls) == 1
    assert "Structured analysis payload" in fake_client.calls[0]["user_prompt"]


def test_build_report_does_not_force_exit_section_for_entry_question():
    fake_client = FakeLLMClient()

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert result["report"] == "LLM Analyst test report."


def test_build_report_removes_exit_section_for_entry_question():
    fake_client = ExitSectionLLMClient()

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert "持有風險 / 出場觀察" not in result["report"]
    assert "This section should not appear" not in result["report"]
    assert "風險提醒" in result["report"]


def test_build_report_for_holding_question_forces_exit_signal_section():
    data = make_success_single_stock_data()
    data["query"] = "MU 如果我已經持有，現在要不要減碼"
    fake_client = FakeLLMClient()

    result = build_report(
        kind="single_stock",
        data=data,
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert "持有風險 / 出場觀察" in result["report"]
    assert "目前 exit signal 為「watch」" in result["report"]
    assert "這是持有風險觀察，不是直接買賣指令。" in result["report"]


def test_build_report_falls_back_when_llm_is_not_configured(monkeypatch):
    clear_llm_env(monkeypatch)

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
    )

    assert result["analyst"]["requested_mode"] == "llm"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["analyst"]["fallback_used"] is True
    assert "MU" in result["report"]


def test_api_accepts_analyst_mode_and_returns_metadata(monkeypatch):
    clear_llm_env(monkeypatch)

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
            user_query="MU now suitable for entry?",
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


def test_theme_llm_payload_includes_news_and_fundamental_summaries():
    payload = build_llm_payload(
        "theme",
        {
            "intent": "industry_trend",
            "status": "success",
            "theme_name": "Memory / Storage",
            "query": "記憶體類股現在適合進場觀察嗎",
            "scan_scope": {"scanned_ticker_count": 2},
            "sector_summary": {"breadth_label": "weak_breadth"},
            "evidence_quality": {
                "news_coverage": "high",
                "fundamental_coverage": "high",
            },
            "results": [
                {
                    "ticker": "MU",
                    "status": "success",
                    "score": -1.75,
                    "reasons": ["below MA20"],
                    "analysis": {
                        "technical_analysis": {"short_term_trend": "weak"},
                        "signals": {"breakout": {"is_breakout": False}},
                        "news_analysis": {
                            "summary": {
                                "total_items": 10,
                                "sentiment": "positive",
                                "high_importance_count": 2,
                                "top_topics": {"product_demand": 4},
                            }
                        },
                        "fundamentals": {
                            "status": "success",
                            "summary": {
                                "stance": "positive",
                                "positives": ["revenue growth"],
                                "risks": [],
                            },
                        },
                        "research_profile": {
                            "technical_score": -1,
                            "news_score": 1,
                            "fundamental_score": 1,
                            "risk_level": "medium",
                        },
                    },
                }
            ],
        },
    )

    assert payload["theme_news_summary"]["total_items"] == 10
    assert payload["theme_news_summary"]["top_topics"] == {"product_demand": 4}
    assert payload["theme_fundamental_summary"]["stance_counts"] == {"positive": 1}
    assert payload["evidence_quality"]["news_coverage"] == "high"
    assert payload["top_results"][0]["news_summary"]["sentiment"] == "positive"
    assert payload["top_results"][0]["fundamental_summary"]["stance"] == "positive"


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


def clear_llm_env(monkeypatch):
    monkeypatch.delenv("MARKET_AGENT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MARKET_AGENT_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_SITE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_APP_NAME", raising=False)
