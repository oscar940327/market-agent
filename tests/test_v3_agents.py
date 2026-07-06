import pandas as pd

import agent.market_manager as market_manager_module
from agent.experts.backtest_agent import select_backtest_strategy
from agent.experts.technical_agent import run_technical_agent
from agent.evidence_agent import run_evidence_agent
from agent.market_data_agent import (
    build_market_data_agent_output,
    build_price_data_window,
    validate_price_data,
)
from agent.market_manager import MarketManagerAgent
from agent.orchestration_policy import build_single_stock_orchestration_summary


def make_price_data(closes, volumes=None):
    if volumes is None:
        volumes = [1000] * len(closes)

    return pd.DataFrame(
        {
            "Close": closes,
            "Volume": volumes,
        },
        index=pd.date_range("2025-01-01", periods=len(closes), freq="D"),
    )


def test_technical_agent_returns_structured_output():
    price_data = make_price_data([10] * 49 + [11], volumes=[100] * 49 + [200])

    result = run_technical_agent(price_data)

    assert result["agent"] == "technical"
    assert result["status"] == "success"
    assert "technical_analysis" in result
    assert "signals" in result
    assert result["summary"]["trend"] in {"strong", "neutral", "weak"}
    assert "rsi14" in result["summary"]
    assert "macd_histogram" in result["summary"]
    assert result["summary"]["momentum_state"] in {
        "bullish_but_overbought",
        "bearish_but_oversold",
        "bullish_momentum",
        "bearish_momentum",
        "turning_positive",
        "turning_negative",
        "neutral",
    }
    assert isinstance(result["summary"]["breakout"], bool)
    assert isinstance(result["summary"]["volume_surge"], bool)
    assert isinstance(result["summary"]["pullback"], bool)


def test_backtest_agent_selects_strategy_from_user_query():
    assert select_backtest_strategy("MU 突破策略以前表現怎麼樣？") == "breakout"
    assert select_backtest_strategy("MU 放量後勝率如何？") == "volume_surge"
    assert select_backtest_strategy("MU 拉回策略以前表現怎麼樣？") == "pullback"
    assert select_backtest_strategy("MU 以前表現怎麼樣？") == "unknown"


def test_market_data_agent_wraps_successful_price_data():
    price_data = make_price_data(list(range(1, 61)))
    price_source = {"provider": "test", "attempted_providers": ["test"], "errors": []}

    result = build_market_data_agent_output(
        ticker="MU",
        period="1y",
        price_data=price_data,
        price_source=price_source,
    )

    assert result["agent"] == "market_data"
    assert result["status"] == "success"
    assert result["payload"]["price_data"].equals(price_data)
    assert result["payload"]["price_source"] == price_source
    assert result["metadata"]["provider"] == "test"
    assert result["fallback_used"] is False


def test_market_data_agent_wraps_validation_error_as_unavailable():
    price_data = make_price_data([1, 2, 3])
    error = validate_price_data(price_data, ticker="MU", min_rows=50)

    result = build_market_data_agent_output(
        ticker="MU",
        period="1y",
        price_data=price_data,
        price_source={"provider": "test"},
        error=error,
    )

    assert result["status"] == "unavailable"
    assert result["payload"]["error"]["status"] == "not_enough_price_data"
    assert result["warnings"]
    assert result["errors"] == []


def test_market_data_agent_builds_required_history_window():
    price_data = make_price_data(list(range(1, 6001)))

    window_data, data_window = build_price_data_window(price_data)

    assert len(window_data) <= len(price_data)
    assert data_window["required_history_years"] == 15
    assert "data_start_date" in data_window
    assert "data_end_date" in data_window
    assert "target_start_date" in data_window


def test_market_manager_single_stock_aggregates_expert_outputs(monkeypatch):
    price_data = make_price_data(list(range(1, 61)))

    def fake_fetch_price_data(ticker, period):
        return price_data, None, {
            "provider": "test",
            "attempted_providers": ["test"],
            "errors": [],
        }

    def fake_news_agent(ticker, include_news=True):
        return {
            "agent": "news",
            "status": "success",
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
            "summary": {
                "sentiment": "neutral",
                "total_items": 0,
                "top_topics": {},
                "high_importance_count": 0,
            },
        }

    def fake_fundamental_agent(ticker, include_fundamentals=True):
        return {
            "agent": "fundamental",
            "status": "skipped",
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
            "summary": {
                "stance": "unknown",
                "positives": [],
                "risks": [],
            },
        }

    monkeypatch.setattr(market_manager_module, "fetch_price_data", fake_fetch_price_data)
    monkeypatch.setattr(market_manager_module, "run_news_agent", fake_news_agent)
    monkeypatch.setattr(
        market_manager_module,
        "run_fundamental_agent",
        fake_fundamental_agent,
    )

    result = MarketManagerAgent().run_single_stock_analysis(
        ticker="MU",
        user_query="MU 現在適合進場嗎？",
        include_news=False,
        include_fundamentals=False,
    )

    assert result["status"] == "success"
    assert result["intent"] == "single_stock_analysis"
    assert result["execution_plan"] == [
        "technical",
        "news_skipped",
        "fundamental_skipped",
    ]
    assert result["orchestration"]["workflow"] == "single_stock"
    assert result["orchestration"]["overall_status"] == "success"
    assert result["orchestration"]["required_agents"] == [
        "market_data",
        "technical",
        "evidence",
    ]
    assert result["orchestration"]["failed_required_agents"] == []
    assert result["orchestration"]["should_alert"] is False
    assert set(result["agent_outputs"]) == {
        "technical",
        "news",
        "fundamental",
        "backtest_evidence",
        "ml_research",
        "evidence",
        "exit_signal",
    }
    assert result["agent_outputs"]["technical"]["agent"] == "technical"
    assert result["agent_outputs"]["news"]["agent"] == "news"
    assert result["agent_outputs"]["fundamental"]["agent"] == "fundamental"
    assert result["technical_analysis"] == result["agent_outputs"]["technical"][
        "technical_analysis"
    ]
    assert result["signals"] == result["agent_outputs"]["technical"]["signals"]
    assert "research_profile" in result
    assert "evidence_quality" in result
    assert result["evidence_quality"]["peer_group"] == "not_used"
    assert (
        result["agent_outputs"]["evidence"]["payload"]["research_profile"]
        == result["research_profile"]
    )
    assert (
        result["agent_outputs"]["evidence"]["payload"]["evidence_quality"]
        == result["evidence_quality"]
    )
    assert "backtest_evidence" in result
    assert "ml_research" in result
    assert result["exit_signal"]["status"] == "success"
    for agent_output in result["agent_outputs"].values():
        assert set(
            [
                "agent",
                "status",
                "summary",
                "payload",
                "warnings",
                "errors",
                "metadata",
                "fallback_used",
            ]
        ).issubset(agent_output)
    assert result["agent_outputs"]["ml_research"]["payload"] == result["ml_research"]
    assert result["agent_outputs"]["exit_signal"]["summary"]["exit_signal"] in {
        "hold",
        "watch",
        "reduce",
        "exit",
    }


def test_orchestration_summary_tracks_required_and_optional_agent_statuses():
    summary = build_single_stock_orchestration_summary(
        {
            "market_data": {
                "status": "success",
                "warnings": [],
                "fallback_used": False,
            },
            "technical": {
                "status": "success",
                "warnings": [],
                "fallback_used": False,
            },
            "evidence": {
                "status": "success",
                "warnings": ["peer_group_not_used"],
                "fallback_used": False,
            },
            "news": {
                "status": "unavailable",
                "warnings": ["news source unavailable"],
                "fallback_used": False,
            },
            "fundamental": {
                "status": "skipped",
                "warnings": [],
                "fallback_used": False,
            },
            "backtest_evidence": {
                "status": "skipped",
                "warnings": [],
                "fallback_used": False,
            },
            "ml_research": {
                "status": "success",
                "warnings": ["runtime fallback"],
                "fallback_used": True,
            },
            "exit_signal": {
                "status": "success",
                "warnings": [],
                "fallback_used": False,
            },
        }
    )

    assert summary["overall_status"] == "success"
    assert summary["failed_required_agents"] == []
    assert summary["unavailable_optional_agents"] == ["news"]
    assert summary["fallback_agents"] == ["ml_research"]
    assert summary["warning_agents"] == ["evidence", "news", "ml_research"]
    assert summary["should_alert"] is False


def test_orchestration_summary_alerts_on_required_agent_failure():
    summary = build_single_stock_orchestration_summary(
        {
            "market_data": {
                "status": "failed",
                "warnings": [],
                "fallback_used": False,
            },
            "technical": {
                "status": "success",
                "warnings": [],
                "fallback_used": False,
            },
            "evidence": {
                "status": "success",
                "warnings": [],
                "fallback_used": False,
            },
        }
    )

    assert summary["overall_status"] == "failed"
    assert summary["failed_required_agents"] == ["market_data"]
    assert summary["should_alert"] is True


def test_evidence_agent_wraps_research_profile_without_changing_shape():
    technical = {
        "short_term_trend": "strong",
        "is_above_ma20": True,
        "momentum_state": "bullish_momentum",
        "rsi14": 55,
    }
    signals = {
        "breakout": {"is_breakout": False},
        "volume_surge": {"is_volume_surge": False},
        "pullback": {"is_pullback": False},
    }
    news_analysis = {
        "summary": {
            "total_items": 0,
            "sentiment": "neutral",
            "sentiment_counts": {},
            "top_topics": {},
            "high_importance_count": 0,
        }
    }
    fundamentals = {
        "status": "skipped",
        "metrics": {},
        "summary": {"stance": "unknown", "positives": [], "risks": []},
    }

    result = run_evidence_agent(
        technical=technical,
        signals=signals,
        news_analysis=news_analysis,
        fundamentals=fundamentals,
        price_history_rows=60,
        include_news=False,
        include_fundamentals=False,
    )

    assert result["agent"] == "evidence"
    assert result["status"] == "success"
    assert result["payload"]["research_profile"]["evidence_quality"] == result[
        "payload"
    ]["evidence_quality"]
    assert result["summary"]["evidence_level"] == result["payload"][
        "evidence_quality"
    ]["level"]


def test_market_manager_single_stock_adds_backtest_evidence_for_triggered_signals(monkeypatch):
    recent_price_data = make_price_data(list(range(1, 90)))
    historical_price_data = make_price_data(list(range(1, 260)))
    captured_periods = []

    def fake_fetch_price_data(ticker, period):
        captured_periods.append(period)
        price_data = recent_price_data if period == "1y" else historical_price_data
        return price_data, None, {
            "provider": "test",
            "attempted_providers": ["test"],
            "errors": [],
        }

    def fake_news_agent(ticker, include_news=True):
        return {
            "agent": "news",
            "ticker": ticker,
            "status": "skipped",
            "news": [],
            "news_analysis": {"summary": {"total_items": 0, "sentiment": "neutral"}},
        }

    def fake_fundamental_agent(ticker, include_fundamentals=True):
        return {
            "agent": "fundamental",
            "ticker": ticker,
            "status": "skipped",
            "fundamentals": {
                "status": "skipped",
                "summary": {"stance": "unknown", "positives": [], "risks": []},
            },
        }

    monkeypatch.setattr(market_manager_module, "fetch_price_data", fake_fetch_price_data)
    monkeypatch.setattr(market_manager_module, "run_news_agent", fake_news_agent)
    monkeypatch.setattr(
        market_manager_module,
        "run_fundamental_agent",
        fake_fundamental_agent,
    )

    result = MarketManagerAgent().run_single_stock_analysis(
        ticker="MU",
        user_query="MU 現在適合進場嗎？",
        include_news=False,
        include_fundamentals=False,
    )

    assert captured_periods == ["1y", "max"]
    assert result["status"] == "success"
    assert result["backtest_evidence"]["status"] == "success"
    assert result["backtest_evidence"]["signals"][0]["strategy"] == "breakout"
    assert set(result["backtest_evidence"]["signals"][0]["horizons"]) == {
        "5",
        "10",
        "20",
    }
    assert (
        result["agent_outputs"]["backtest_evidence"]["payload"]
        == result["backtest_evidence"]
    )


def test_market_manager_single_stock_skips_backtest_evidence_fetch_without_triggered_signals(monkeypatch):
    price_data = make_price_data(list(range(100, 40, -1)))
    captured_periods = []

    def fake_fetch_price_data(ticker, period):
        captured_periods.append(period)
        return price_data, None, {
            "provider": "test",
            "attempted_providers": ["test"],
            "errors": [],
        }

    def fake_news_agent(ticker, include_news=True):
        return {
            "agent": "news",
            "ticker": ticker,
            "status": "skipped",
            "news": [],
            "news_analysis": {"summary": {"total_items": 0, "sentiment": "neutral"}},
        }

    def fake_fundamental_agent(ticker, include_fundamentals=True):
        return {
            "agent": "fundamental",
            "ticker": ticker,
            "status": "skipped",
            "fundamentals": {
                "status": "skipped",
                "summary": {"stance": "unknown", "positives": [], "risks": []},
            },
        }

    monkeypatch.setattr(market_manager_module, "fetch_price_data", fake_fetch_price_data)
    monkeypatch.setattr(market_manager_module, "run_news_agent", fake_news_agent)
    monkeypatch.setattr(
        market_manager_module,
        "run_fundamental_agent",
        fake_fundamental_agent,
    )

    result = MarketManagerAgent().run_single_stock_analysis(
        ticker="MU",
        user_query="MU 現在適合進場嗎？",
        include_news=False,
        include_fundamentals=False,
    )

    assert captured_periods == ["1y"]
    assert result["backtest_evidence"]["status"] == "no_triggered_signals"
    assert result["backtest_evidence"]["signals"] == []


def test_market_manager_backtest_includes_agent_output(monkeypatch):
    price_data = make_price_data(list(range(1, 6001)))
    captured = {}

    def fake_fetch_price_data(ticker, period):
        captured["period"] = period
        return price_data, None, {
            "provider": "test",
            "attempted_providers": ["test"],
            "errors": [],
        }

    monkeypatch.setattr(market_manager_module, "fetch_price_data", fake_fetch_price_data)

    result = MarketManagerAgent().run_backtest_query(
        ticker="MU",
        user_query="MU 突破策略以前表現怎麼樣？",
    )

    assert result["status"] == "success"
    assert result["intent"] == "backtest_query"
    assert captured["period"] == "max"
    assert result["execution_plan"] == ["backtest_strategy_selection", "backtest"]
    assert result["agent_outputs"]["backtest"]["agent"] == "backtest"
    assert result["report"] == result["agent_outputs"]["backtest"]["report"]
    assert result["data_start_date"] == result["data_window"]["data_start_date"]
    assert result["data_as_of"] == result["data_window"]["data_as_of"]
    assert result["evidence_quality"]["required_history_years"] == 15
    assert result["evidence_quality"]["peer_group"] == "not_used"
    assert result["data_freshness"]["overall"] == "fresh"
    assert result["data_freshness"]["source"] == "backtest_price_window"
    assert result["data_freshness"]["data_as_of"] == result["data_window"]["data_as_of"]
    assert result["ml_reference"]["status"] == "skipped"
    assert result["ml_reference"]["source"]["type"] == "not_applicable"
