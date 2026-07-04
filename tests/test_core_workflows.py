import pandas as pd

from agent.rule_based_router import detect_intent
from agent.exit_signal import build_exit_signal
from agent.research_profile import build_research_profile
from backtesting.metrics import calculate_backtest_metrics
from backtesting.evidence import build_backtest_evidence_quality
from backtesting.reports import build_backtest_report
from backtesting.signal_evidence import build_signal_backtest_evidence
import main as main_module
from data.themes import (
    find_theme_key,
    get_all_theme_tickers,
)
from main import build_sector_summary, run_theme_analysis, score_stock_analysis, validate_price_data
from skills.news_analysis_skill import analyze_news_items
from skills.fundamental_skill import summarize_fundamentals
from strategies.breakout_strategy import check_breakout
from strategies.pullback_strategy import check_pullback_to_ma20
from strategies.volume_surge_strategy import check_volume_surge
from skills.technical_analysis_skill import analyze_moving_averages


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


def test_detect_intent_routes_plain_chinese_strategy_history_to_backtest():
    result = detect_intent("MU 突破策略以前表現怎麼樣")

    assert result["intent"] == "backtest_query"
    assert result["has_ticker"] is True


def test_detect_intent_routes_single_ticker_holding_question_to_stock_analysis():
    result = detect_intent("MU 如果我已經持有，現在要不要減碼")

    assert result["intent"] == "single_stock_analysis"
    assert result["has_ticker"] is True


def test_detect_intent_routes_supported_theme_query():
    result = detect_intent("記憶體概念股有哪些值得觀察？")

    assert result["intent"] == "industry_trend"


def test_detect_intent_routes_theme_question_before_generic_entry_terms():
    result = detect_intent("記憶體類股現在適合進場觀察嗎？")

    assert result["intent"] == "industry_trend"
    assert result["has_ticker"] is False


def test_detect_intent_routes_ticker_question_to_single_stock():
    result = detect_intent("MU 現在適合進場嗎？")

    assert result["intent"] == "single_stock_analysis"
    assert result["has_ticker"] is True


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


def test_technical_analysis_includes_rsi_macd_and_momentum_state():
    price_data = make_price_data(list(range(1, 61)))

    result = analyze_moving_averages(price_data)

    assert result["rsi14"] == 100
    assert "macd" in result
    assert "macd_signal" in result
    assert "macd_histogram" in result
    assert result["momentum_state"] == "bullish_but_overbought"


def test_exit_signal_detects_reduce_when_price_breaks_ma20_with_weak_momentum():
    result = build_exit_signal(
        technical={
            "current_price": 95,
            "ma20": 100,
            "ma50": 90,
            "short_term_trend": "weak",
            "rsi14": 42,
            "macd_histogram": -1.2,
            "momentum_state": "bearish_momentum",
        },
        signals={},
        ml_research={
            "status": "success",
            "source": {"type": "saved_daily_prediction"},
            "targets": {
                "large_drop_20d": {
                    "probability": 0.72,
                    "label": "high large-drop risk",
                }
            },
        },
    )

    assert result["status"] == "success"
    assert result["exit_signal"] == "reduce"
    assert result["weakening_signal_20d"] == "high"
    assert result["email_alert_eligible"] is True
    assert "below_ma20" in result["risk_flags"]
    assert result["ml_reference_used"] is True


def test_exit_signal_watches_ma20_break_without_macd_weakening():
    result = build_exit_signal(
        technical={
            "current_price": 95,
            "ma20": 100,
            "ma50": 90,
            "short_term_trend": "weak",
            "rsi14": 48,
            "macd_histogram": 0.5,
            "momentum_state": "turning_positive",
        },
        signals={},
        ml_research={"status": "unavailable"},
    )

    assert result["exit_signal"] == "watch"
    assert result["email_alert_eligible"] is False
    assert "below_ma20" in result["risk_flags"]
    assert "below_ma20_with_negative_macd" not in result["risk_flags"]


def test_exit_signal_stays_hold_when_trend_and_momentum_are_stable():
    result = build_exit_signal(
        technical={
            "current_price": 110,
            "ma20": 100,
            "ma50": 90,
            "short_term_trend": "strong",
            "rsi14": 58,
            "macd_histogram": 1.2,
            "momentum_state": "bullish_momentum",
        },
        signals={},
        ml_research={"status": "unavailable"},
    )

    assert result["exit_signal"] == "hold"
    assert result["weakening_signal_20d"] == "low"
    assert result["email_alert_eligible"] is False


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


def test_backtest_evidence_quality_rewards_large_positive_full_history_sample():
    result = build_backtest_evidence_quality(
        metrics={
            "total_trades": 35,
            "win_rate": 0.6,
            "average_return": 0.03,
            "max_loss": -0.05,
        },
        data_window={
            "history_years": 15.0,
            "required_history_years": 15,
            "has_required_history": True,
            "data_start_date": "2011-06-25",
            "data_end_date": "2026-06-25",
            "data_as_of": "2026-06-25",
        },
    )

    assert result["level"] == "high"
    assert result["backtest_sample"] == "high"
    assert result["news_coverage"] == "not_applicable"
    assert result["social_coverage"] == "not_used"
    assert result["fundamental_coverage"] == "not_applicable"
    assert result["market_wide"] == "not_used"
    assert result["sample_quality"] == "high"
    assert result["market_cycle_coverage"] == "sufficient"
    assert result["peer_group_needed"] is False


def test_backtest_evidence_quality_marks_short_history_as_peer_group_needed():
    result = build_backtest_evidence_quality(
        metrics={
            "total_trades": 18,
            "win_rate": 0.55,
            "average_return": 0.02,
            "max_loss": -0.06,
        },
        data_window={
            "history_years": 4.2,
            "required_history_years": 15,
            "has_required_history": False,
            "data_start_date": "2022-04-01",
            "data_end_date": "2026-06-25",
            "data_as_of": "2026-06-25",
        },
    )

    assert result["level"] == "low_to_medium"
    assert result["market_cycle_coverage"] == "insufficient"
    assert result["peer_group_needed"] is True
    assert result["peer_group"] == "not_used"
    assert "未達 15 年需求" in result["reason"]


def test_backtest_evidence_quality_marks_zero_samples_as_none():
    result = build_backtest_evidence_quality(
        metrics={
            "total_trades": 0,
            "win_rate": 0,
            "average_return": 0,
            "max_loss": 0,
        },
        data_window={
            "history_years": 15.0,
            "required_history_years": 15,
            "has_required_history": True,
        },
    )

    assert result["level"] == "none"
    assert result["sample_quality"] == "none"
    assert "沒有符合條件的交易" in result["reason"]


def test_signal_backtest_evidence_returns_no_triggered_signal_status():
    price_data = make_price_data(list(range(1, 120)))

    result = build_signal_backtest_evidence(
        ticker="MU",
        price_data=price_data,
        current_signals={
            "breakout": {"is_breakout": False},
            "volume_surge": {"is_volume_surge": False},
            "pullback": {"is_pullback": False},
        },
        data_window={
            "history_years": 15,
            "has_required_history": True,
        },
    )

    assert result["status"] == "no_triggered_signals"
    assert result["signals"] == []


def test_signal_backtest_evidence_reports_all_triggered_signals_and_horizons():
    closes = list(range(1, 220))
    volumes = [1000] * len(closes)
    for index in range(25, len(volumes), 25):
        volumes[index] = 3000
    price_data = make_price_data(closes, volumes=volumes)

    result = build_signal_backtest_evidence(
        ticker="MU",
        price_data=price_data,
        current_signals={
            "breakout": {"is_breakout": True},
            "volume_surge": {"is_volume_surge": True},
            "pullback": {"is_pullback": False},
        },
        data_window={
            "history_years": 15,
            "has_required_history": True,
            "data_start_date": "2011-01-01",
            "data_end_date": "2026-01-01",
            "data_as_of": "2026-01-01",
        },
    )

    assert result["status"] == "success"
    assert result["summary"]["triggered_signal_count"] == 2
    assert [signal["strategy"] for signal in result["signals"]] == [
        "breakout",
        "volume_surge",
    ]

    for signal in result["signals"]:
        assert set(signal["horizons"]) == {"5", "10", "20"}
        assert signal["sample_size"] == signal["horizons"]["20"]["sample_size"]
        assert signal["evidence_quality"]["peer_group"] == "not_used"
        assert signal["evidence_quality"]["level"] in {
            "low",
            "low_to_medium",
            "medium",
            "high",
        }


def test_score_stock_analysis_rewards_positive_signals():
    analysis_data = {
        "ticker": "MU",
        "status": "success",
        "technical_analysis": {
            "short_term_trend": "strong",
            "is_above_ma20": True,
            "momentum_state": "bullish_momentum",
        },
        "signals": {
            "breakout": {"is_breakout": True},
            "volume_surge": {"is_volume_surge": True},
            "pullback": {"is_pullback": False},
        },
    }

    result = score_stock_analysis(analysis_data)

    assert result["score"] == 8.0
    assert "短線趨勢偏強" in result["reasons"]
    assert "RSI 與 MACD 多方動能增強" in result["reasons"]
    assert "出現突破訊號" in result["reasons"]


def test_find_theme_key_and_all_theme_tickers_are_stable():
    assert find_theme_key("AI server 相關股票有哪些值得觀察？") == "ai_server"
    assert find_theme_key("資安股有哪些值得觀察？") == "cybersecurity"
    assert find_theme_key("雲端軟體股有哪些值得觀察？") == "software_cloud"
    assert find_theme_key("能源股有哪些值得觀察？") == "energy_utilities"
    assert find_theme_key("醫療生技股有哪些值得觀察？") == "healthcare_biotech"

    tickers = get_all_theme_tickers()

    assert "NVDA" in tickers
    assert "ADBE" not in tickers
    assert len(tickers) == len(set(tickers))


def test_non_default_theme_tickers_are_available_for_ticker_detection():
    default_tickers = get_all_theme_tickers()
    all_theme_tickers = get_all_theme_tickers(include_non_default=True)

    assert "ADBE" not in default_tickers
    assert "ADBE" in all_theme_tickers
    assert "CRWD" in all_theme_tickers
    assert "FANG" in all_theme_tickers
    assert len(all_theme_tickers) == len(set(all_theme_tickers))


def test_run_theme_analysis_scans_matched_theme(monkeypatch):
    captured_tickers = []
    captured_options = []

    def fake_run_single_stock_analysis(
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
        include_ml=True,
    ):
        captured_tickers.append(ticker)
        captured_options.append(
            {
                "include_news": include_news,
                "include_fundamentals": include_fundamentals,
                "include_ml": include_ml,
            }
        )
        return {
            "ticker": ticker,
            "status": "success",
            "technical_analysis": {
                "short_term_trend": "strong",
                "is_above_ma20": True,
                "momentum_state": "neutral",
            },
            "signals": {
                "breakout": {"is_breakout": False},
                "volume_surge": {"is_volume_surge": False},
                "pullback": {"is_pullback": False},
            },
        }

    monkeypatch.setattr(
        main_module,
        "run_single_stock_analysis",
        fake_run_single_stock_analysis,
    )

    result = run_theme_analysis("資安股有哪些值得觀察？")

    assert result["theme_key"] == "cybersecurity"
    assert result["scan_scope"] == {
        "available_ticker_count": 4,
        "scanned_ticker_count": 4,
        "scan_limit": None,
        "scan_limited": False,
    }
    assert captured_tickers == ["CRWD", "FTNT", "PANW", "ZS"]
    assert all(option["include_news"] is True for option in captured_options)
    assert all(option["include_fundamentals"] is True for option in captured_options)
    assert all(option["include_ml"] is False for option in captured_options)


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
            "momentum_state": "neutral",
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
                "sentiment_counts": {"positive": 2},
                "high_importance_count": 1,
                "top_topics": {"earnings": 1},
            }
        },
        fundamentals={
            "status": "success",
            "metrics": {
                "trailing_pe": 20,
                "forward_pe": 18,
                "revenue_growth": 0.1,
                "earnings_growth": 0.2,
                "gross_margins": 0.5,
                "debt_to_equity": 20,
            },
            "summary": {
                "positives": ["營收成長為正", "毛利率相對較高"],
                "risks": ["本益比偏高"],
            },
        },
        price_history_rows=220,
    )

    assert result["technical_score"] == 6.5
    assert result["news_score"] == 1.0
    assert result["fundamental_score"] == 0.75
    assert result["risk_score"] == 0
    assert result["setup_quality"] == "strong"
    assert result["risk_level"] == "low"
    assert result["research_confidence"] == "high"
    assert result["evidence_quality"]["level"] == "high"
    assert result["evidence_quality"]["news_coverage"] == "medium"
    assert result["evidence_quality"]["social_coverage"] == "not_used"
    assert result["evidence_quality"]["fundamental_coverage"] == "high"


def test_build_research_profile_marks_partial_evidence_without_peer_or_market_claims():
    result = build_research_profile(
        technical={
            "short_term_trend": "neutral",
            "is_above_ma20": True,
            "momentum_state": "turning_positive",
        },
        signals={
            "breakout": {"is_breakout": False},
            "volume_surge": {"is_volume_surge": False},
            "pullback": {"is_pullback": False},
        },
        news_analysis={
            "summary": {
                "total_items": 0,
                "sentiment": "neutral",
            }
        },
        fundamentals={
            "status": "skipped",
            "summary": {
                "positives": [],
                "risks": [],
            },
        },
        price_history_rows=80,
        include_news=False,
        include_fundamentals=False,
    )

    assert result["evidence_quality"]["level"] == "low_to_medium"
    assert result["evidence_quality"]["stock_specific"] == "low_to_medium"
    assert result["evidence_quality"]["backtest_sample"] == "not_applicable"
    assert result["evidence_quality"]["news_coverage"] == "skipped"
    assert result["evidence_quality"]["social_coverage"] == "not_used"
    assert result["evidence_quality"]["fundamental_coverage"] == "skipped"
    assert result["evidence_quality"]["peer_group"] == "not_used"
    assert result["evidence_quality"]["market_wide"] == "not_used"
    assert "尚未使用同產業或全市場相似情境樣本" in result["evidence_quality"]["reason"]


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


def test_run_theme_analysis_includes_evidence_quality(monkeypatch):
    def fake_run_single_stock_analysis(
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
        include_ml=True,
    ):
        return {
            "ticker": ticker,
            "status": "success",
            "technical_analysis": {
                "short_term_trend": "strong",
                "is_above_ma20": True,
                "momentum_state": "neutral",
            },
            "signals": {
                "breakout": {"is_breakout": False},
                "volume_surge": {"is_volume_surge": False},
                "pullback": {"is_pullback": False},
            },
        }

    monkeypatch.setattr(
        main_module,
        "run_single_stock_analysis",
        fake_run_single_stock_analysis,
    )

    result = run_theme_analysis("資安股有哪些值得觀察？")

    assert result["evidence_quality"]["level"] == "medium"
    assert result["evidence_quality"]["backtest_sample"] == "not_applicable"
    assert result["evidence_quality"]["news_coverage"] == "high"
    assert result["evidence_quality"]["social_coverage"] == "not_used"
    assert result["evidence_quality"]["fundamental_coverage"] == "high"
    assert result["evidence_quality"]["peer_group"] == "not_used"
    assert result["evidence_quality"]["market_wide"] == "not_used"
