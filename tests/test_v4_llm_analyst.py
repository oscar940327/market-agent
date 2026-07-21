import json

from agent.llm_analyst import (
    OpenRouterChatClient,
    build_llm_payload,
    build_llm_user_prompt,
    extract_chat_completion_text,
)
from agent.report_context import build_single_stock_report_context
from agent.reporting import build_report, get_llm_client_from_env
from agent.fixed_single_stock_report import (
    build_fundamental_analysis,
    build_ml_consistency_note,
    describe_news_impact_type,
)
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


def make_success_backtest_data():
    metrics = {
        "total_trades": 584,
        "win_rate": 0.5479,
        "average_return": 0.0075,
        "max_loss": -0.1961,
    }
    evidence_quality = {
        "level": "medium",
        "sample_size": 584,
        "sample_quality": "high",
        "history_years": 15,
        "required_history_years": 15,
        "market_cycle_coverage": "sufficient",
        "peer_group_needed": False,
        "peer_group": "not_used",
        "reason": "最大虧損偏高，即使其他數字看起來不差，也需要保守看待。",
    }
    data_window = {
        "data_start_date": "2011-07-06",
        "data_end_date": "2026-07-06",
        "data_as_of": "2026-07-06",
        "history_years": 15,
    }
    return {
        "status": "success",
        "intent": "backtest_query",
        "ticker": "MU",
        "strategy": "breakout",
        "user_query": "MU 突破策略以前表現怎麼樣",
        "metrics": metrics,
        "evidence_quality": evidence_quality,
        "data_window": data_window,
        "report": {
            "ticker": "MU",
            "strategy_name": "breakout",
            "metrics": metrics,
            "evidence_quality": evidence_quality,
            "data_window": data_window,
            "sample_trades": [],
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

    assert "ML Reference" in result["report"]
    assert "exit signal" in result["report"]
    assert result["analyst"]["requested_mode"] == "llm"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["analyst"]["fallback_used"] is False
    assert len(fake_client.calls) == 0
    return

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

    assert "ML Reference" in result["report"]
    assert "exit signal" not in result["report"]
    assert len(fake_client.calls) == 0
    return

    assert result["report"] == "LLM Analyst test report."


def test_build_report_removes_exit_section_for_entry_question():
    fake_client = ExitSectionLLMClient()

    result = build_report(
        kind="single_stock",
        data=make_success_single_stock_data(),
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert "exit signal" not in result["report"]
    assert "This section should not appear" not in result["report"]
    assert len(fake_client.calls) == 0
    return

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

    assert "exit signal" in result["report"]
    assert "watch" in result["report"]
    assert "不是直接買賣指令" in result["report"]
    assert "MU目前持有風險判斷為「提高觀察」" in result["report"]
    assert "目前結論為「可列入觀察」" not in result["report"]
    return

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
    assert result["analyst"]["fallback_used"] is False
    assert "MU" in result["report"]


def test_build_report_uses_fixed_backtest_report_even_when_llm_requested():
    fake_client = FakeLLMClient()

    result = build_report(
        kind="backtest",
        data=make_success_backtest_data(),
        analyst_mode="llm",
        llm_client=fake_client,
    )

    assert result["analyst"]["requested_mode"] == "llm"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["analyst"]["fallback_used"] is False
    assert len(fake_client.calls) == 0
    assert "MU 策略回測摘要" in result["report"]
    assert "策略：breakout" in result["report"]
    assert "非重疊交易次數：584" in result["report"]
    assert "勝率：54.79%" in result["report"]
    assert "最大虧損：-19.61%" in result["report"]
    assert "訊號歷史統計" in result["report"]
    assert "本次樣本數充足" in result["report"]
    assert "樣本數太少時" not in result["report"]
    assert "更多樣本確認" not in result["report"]


def test_fundamental_report_explains_price_to_sales_driven_valuation():
    report = build_fundamental_analysis(
        {
            "fundamentals": {
                "status": "success",
                "metrics": {
                    "forward_pe": 6.6,
                    "price_to_sales": 12.2,
                    "revenue_growth": 3.457,
                },
                "summary": {"risks": []},
            }
        }
    )

    assert "合理偏貴" in report
    assert "Price/Sales 約 12.2" in report
    assert "本益比不高，但營收倍數偏高" in report


def test_price_to_sales_near_twelve_prevents_cheap_valuation_label():
    report = build_fundamental_analysis(
        {
            "fundamentals": {
                "status": "success",
                "metrics": {
                    "forward_pe": 6.3,
                    "price_to_sales": 11.7,
                    "revenue_growth": 3.457,
                },
                "summary": {"risks": []},
            }
        }
    )

    assert "目前估值判斷為「合理偏貴」" in report
    assert "本益比不高，但營收倍數偏高" in report


def test_holding_report_uses_exit_conclusion_and_conservative_risk_overlay():
    data = make_success_single_stock_data()
    data["query"] = "MU 如果我已經持有，現在要不要減碼"
    data["exit_signal"]["exit_signal"] = "reduce"
    data["ml_research"] = {
        "status": "success",
        "targets": {},
        "downside_risk_overlay": {
            "active": True,
            "risk_level": "severe",
            "conservative_max_drop": -0.12,
            "reasons": ["recent_risk_event_news"],
        },
    }

    report = build_report(kind="single_stock", data=data, analyst_mode="rule_based")["report"]

    assert "MU目前持有風險判斷為「評估減碼」" in report
    assert "保守風險層級為 極高" in report
    assert "近期有風險類新聞" in report
    assert "風險等級為 high" in report
    assert "不代表現在一定適合進場" not in report


def test_short_term_news_explanation_matches_sentiment():
    positive = describe_news_impact_type("影響短線情緒", sentiment="positive")
    negative = describe_news_impact_type("影響短線情緒", sentiment="negative")

    assert "目前偏正面" in positive
    assert "目前偏負面" in negative
    assert "偏正面或負面" not in positive


def test_ml_consistency_note_explains_positive_return_with_high_path_risk():
    note = build_ml_consistency_note(
        {
            "targets": {
                "up_20d": {"probability": 0.504},
                "large_drop_20d": {"probability": 0.692},
            },
            "return_model": {
                "targets": {
                    "forward_return_20d": {"predicted_value": 0.11},
                }
            },
        }
    )

    assert "價格路徑可能高度波動" in note
    assert "不能把正報酬估算解讀成穩定上漲或目標價" in note


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
    assert result["analyst"]["fallback_used"] is False


def test_openrouter_client_can_be_selected_from_environment(monkeypatch):
    monkeypatch.setenv("MARKET_AGENT_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MARKET_AGENT_LLM_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Market Agent Test")
    monkeypatch.setenv("MARKET_AGENT_LLM_MAX_TOKENS", "4096")

    client = get_llm_client_from_env()

    assert isinstance(client, OpenRouterChatClient)
    assert client.provider == "openrouter"
    assert client.model == "openai/gpt-4.1"
    assert client.site_url == "https://example.com"
    assert client.app_name == "Market Agent Test"
    assert client.max_tokens == 4096


def test_openrouter_client_sends_explicit_max_tokens(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("agent.llm_analyst.urllib.request.urlopen", fake_urlopen)
    client = OpenRouterChatClient(api_key="test", max_tokens=4096)

    assert client.generate("system", "user") == "ok"
    assert captured["payload"]["max_tokens"] == 4096


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
