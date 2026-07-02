import pandas as pd

import agent.market_manager as market_manager_module
from agent.experts.backtest_agent import select_backtest_strategy
from agent.experts.technical_agent import run_technical_agent
from agent.market_manager import MarketManagerAgent


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
    assert set(result["agent_outputs"]) == {
        "technical",
        "news",
        "fundamental",
        "backtest_evidence",
        "ml_research",
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
    assert "backtest_evidence" in result
    assert "ml_research" in result
    assert result["exit_signal"]["status"] == "success"
    assert result["agent_outputs"]["ml_research"] == result["ml_research"]
    assert result["agent_outputs"]["exit_signal"]["summary"]["exit_signal"] in {
        "hold",
        "watch",
        "reduce",
        "exit",
    }


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
    assert result["agent_outputs"]["backtest_evidence"] == result["backtest_evidence"]


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
