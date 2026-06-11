import pandas as pd

from agent.rule_based_router import detect_intent
from agent.research_profile import build_research_profile
from backtesting.metrics import calculate_backtest_metrics
from backtesting.reports import build_backtest_report
from data.themes import find_theme_key, get_all_theme_tickers
from main import build_sector_summary, score_stock_analysis, validate_price_data
from skills.news_analysis_skill import analyze_news_items
from skills.fundamental_skill import summarize_fundamentals
from strategies.breakout_strategy import check_breakout
from strategies.pullback_strategy import check_pullback_to_ma20
from strategies.volume_surge_strategy import check_volume_surge


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


def test_detect_intent_routes_backtest_before_single_stock():
    result = detect_intent("MU 突破策略以前表現怎麼樣？")

    assert result["intent"] == "backtest_query"


def test_detect_intent_routes_supported_theme_query():
    result = detect_intent("記憶體概念股有哪些值得觀察？")

    assert result["intent"] == "industry_trend"


def test_validate_price_data_rejects_missing_required_columns():
    price_data = pd.DataFrame({"Close": [1, 2, 3]})

    result = validate_price_data(price_data, ticker="MU", min_rows=2)

    assert result["status"] == "invalid_price_data"
    assert "Volume" in result["message"]


def test_validate_price_data_rejects_short_history():
    price_data = make_price_data([10, 11, 12])

    result = validate_price_data(price_data, ticker="MU", min_rows=5)

    assert result["status"] == "not_enough_price_data"
    assert "目前只有 3 筆資料" in result["message"]


def test_breakout_signal_compares_latest_close_to_previous_high():
    price_data = make_price_data([10] * 20 + [11])

    result = check_breakout(price_data, lookback_days=20)

    assert result["is_breakout"] is True
    assert result["latest_close"] == 11
    assert result["previous_high"] == 10


def test_volume_surge_signal_uses_previous_average_volume():
    price_data = make_price_data([10] * 21, volumes=[100] * 20 + [200])

    result = check_volume_surge(
        price_data,
        lookback_days=20,
        surge_multiplier=1.5,
    )

    assert result["is_volume_surge"] is True
    assert result["volume_ratio"] == 2


def test_pullback_signal_detects_price_near_ma20():
    price_data = make_price_data([100] * 19 + [102])

    result = check_pullback_to_ma20(price_data, tolerance=0.03)

    assert result["is_pullback"] is True
    assert result["is_near_ma20"] is True


def test_calculate_backtest_metrics_handles_wins_losses_and_average():
    metrics = calculate_backtest_metrics(
        [
            {"return_pct": 0.10},
            {"return_pct": -0.05},
            {"return_pct": 0.00},
        ]
    )

    assert metrics == {
        "total_trades": 3,
        "win_rate": 0.3333,
        "average_return": 0.0167,
        "max_loss": -0.05,
    }


def test_build_backtest_report_limits_sample_trades_to_first_five():
    trades = [{"return_pct": index / 100} for index in range(6)]
    metrics = calculate_backtest_metrics(trades)

    report = build_backtest_report(
        ticker="MU",
        strategy_name="breakout",
        backtest_results=trades,
        metrics=metrics,
    )

    assert report["ticker"] == "MU"
    assert report["strategy_name"] == "breakout"
    assert report["sample_trades"] == trades[:5]


def test_score_stock_analysis_rewards_positive_signals():
    analysis_data = {
        "ticker": "MU",
        "status": "success",
        "technical_analysis": {
            "short_term_trend": "strong",
            "is_above_ma20": True,
        },
        "signals": {
            "breakout": {"is_breakout": True},
            "volume_surge": {"is_volume_surge": True},
            "pullback": {"is_pullback": False},
        },
    }

    result = score_stock_analysis(analysis_data)

    assert result["score"] == 6.5
    assert "短線趨勢偏強" in result["reasons"]
    assert "出現突破訊號" in result["reasons"]


def test_find_theme_key_and_all_theme_tickers_are_stable():
    assert find_theme_key("AI server 相關股票有哪些值得觀察？") == "ai_server"

    tickers = get_all_theme_tickers()

    assert "NVDA" in tickers
    assert len(tickers) == len(set(tickers))


def test_analyze_news_items_classifies_topic_sentiment_and_importance():
    result = analyze_news_items(
        [
            {
                "title": "MU beats earnings expectations and raises guidance",
                "link": "https://example.com/positive",
                "published": "Fri, 12 Jun 2026 00:00:00 GMT",
            },
            {
                "title": "Chip demand warning pressures memory stocks",
                "link": "https://example.com/negative",
                "published": "Fri, 12 Jun 2026 01:00:00 GMT",
            },
        ]
    )

    assert result["summary"]["total_items"] == 2
    assert result["summary"]["sentiment"] == "neutral"
    assert result["summary"]["high_importance_count"] == 2
    assert result["items"][0]["topic"] == "earnings"
    assert result["items"][0]["sentiment"] == "positive"
    assert result["items"][0]["importance"] == "high"
    assert result["items"][1]["topic"] == "industry_demand"
    assert result["items"][1]["sentiment"] == "negative"


def test_summarize_fundamentals_identifies_positive_and_risk_factors():
    result = summarize_fundamentals(
        {
            "revenue_growth": 0.12,
            "earnings_growth": -0.05,
            "gross_margins": 0.45,
            "debt_to_equity": 170,
            "trailing_pe": 65,
        }
    )

    assert result["stance"] == "mixed"
    assert "營收成長為正" in result["positives"]
    assert "毛利率相對較高" in result["positives"]
    assert "獲利成長為負" in result["risks"]
    assert "負債權益比偏高" in result["risks"]
    assert "本益比偏高" in result["risks"]


def test_build_research_profile_combines_multiple_research_dimensions():
    result = build_research_profile(
        technical={
            "short_term_trend": "strong",
            "is_above_ma20": True,
        },
        signals={
            "breakout": {"is_breakout": True},
            "volume_surge": {"is_volume_surge": True},
            "pullback": {"is_pullback": False},
        },
        news_analysis={
            "summary": {
                "total_items": 2,
                "sentiment": "positive",
            }
        },
        fundamentals={
            "status": "success",
            "summary": {
                "positives": ["營收成長為正", "毛利率相對較高"],
                "risks": ["本益比偏高"],
            },
        },
    )

    assert result["technical_score"] == 6.5
    assert result["news_score"] == 1.0
    assert result["fundamental_score"] == 0.75
    assert result["risk_score"] == 0
    assert result["setup_quality"] == "strong"
    assert result["risk_level"] == "low"
    assert result["research_confidence"] == "high"


def test_build_sector_summary_measures_theme_breadth():
    result = build_sector_summary(
        [
            {"ticker": "MU", "status": "success", "score": 4},
            {"ticker": "WDC", "status": "success", "score": 2},
            {"ticker": "STX", "status": "success", "score": -1},
            {"ticker": "SNDK", "status": "price_data_error", "score": 0},
        ]
    )

    assert result == {
        "successful_count": 3,
        "average_score": 1.67,
        "strongest_ticker": "MU",
        "positive_breadth": 0.6667,
        "breadth_label": "mixed",
    }
