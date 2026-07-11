import pandas as pd

import backtesting.backtest_runner as backtest_runner
from agent.fixed_single_stock_report import describe_momentum_state
from agent.llm_analyst import LLM_ANALYST_SYSTEM_PROMPT
from backtesting.signal_evidence import (
    SIGNAL_DEFINITIONS,
    collect_signal_event_indices,
)
from ml_model_improvement import (
    apply_downside_risk_overlay,
    build_current_downside_feature_snapshot,
)


def make_price_data(length=120):
    return pd.DataFrame(
        {
            "Close": [100 + index * 0.2 for index in range(length)],
            "Volume": [1000] * length,
        },
        index=pd.date_range("2026-01-01", periods=length, freq="B"),
    )


def make_ml_research():
    return {
        "status": "success",
        "targets": {
            "large_drop_20d": {
                "probability": 0.20,
                "signal_quality": "medium",
            }
        },
        "return_model": {
            "status": "success",
            "targets": {
                "max_drop_20d": {
                    "predicted_value": -0.04,
                    "predicted_percent": -4.0,
                    "predicted_range": {
                        "low": -0.06,
                        "high": -0.02,
                        "low_percent": -6.0,
                        "high_percent": -2.0,
                    },
                }
            },
        },
    }


def test_current_query_snapshot_replaces_conflicting_saved_technical_overlay():
    ml_research = make_ml_research()
    saved_overlay = apply_downside_risk_overlay(
        ml_research,
        {
            "price_vs_ma20": -0.08,
            "macd_histogram": -2.0,
            "volatility_20d": 0.05,
            "market_regime": "bear",
            "market_snapshot": {
                "technical_state": "bearish",
                "risk_state": "high",
            },
        },
    )
    assert saved_overlay["return_model"]["targets"]["max_drop_20d"][
        "predicted_value"
    ] == -0.14

    price_data = make_price_data()
    current_snapshot = build_current_downside_feature_snapshot(
        price_data=price_data,
        technical={
            "current_price": 124,
            "ma20": 120,
            "macd_histogram": 1.5,
        },
        signals={
            "breakout": {"is_breakout": False},
            "volume_surge": {"is_volume_surge": False},
            "pullback": {"is_pullback": False},
        },
        ml_research=ml_research,
        base_snapshot={
            "market_regime": "bull",
            "market_snapshot": {"market_regime": "bull"},
        },
        risk_event_count=0,
    )
    refreshed = apply_downside_risk_overlay(saved_overlay, current_snapshot)

    overlay = refreshed["downside_risk_overlay"]
    target = refreshed["return_model"]["targets"]["max_drop_20d"]
    assert overlay["active"] is False
    assert overlay["feature_source"] == "current_query_technical_with_saved_market_context"
    assert "price_below_ma20" not in overlay["reasons"]
    assert "macd_histogram_negative" not in overlay["reasons"]
    assert target["predicted_value"] == -0.04
    assert "overlay_applied" not in target


def test_strategy_backtest_skips_overlapping_holding_periods(monkeypatch):
    monkeypatch.setattr(
        backtest_runner,
        "check_pullback_to_ma20",
        lambda _data: {"is_pullback": True},
    )

    trades = backtest_runner.run_pullback_backtest(
        make_price_data(80),
        holding_days=5,
    )
    signal_dates = [pd.Timestamp(trade["signal_date"]) for trade in trades]

    assert len(trades) == 5
    assert all(
        (later - earlier).days >= 5
        for earlier, later in zip(signal_dates, signal_dates[1:])
    )


def test_historical_signal_evidence_uses_non_overlapping_20_day_samples(monkeypatch):
    monkeypatch.setitem(
        SIGNAL_DEFINITIONS["pullback"],
        "checker",
        lambda _data: {"is_pullback": True},
    )

    indices = collect_signal_event_indices(
        price_data=make_price_data(130),
        strategy="pullback",
    )

    assert indices == [50, 70, 90]


def test_momentum_wording_matches_current_state_names():
    assert "多方動能增強" in describe_momentum_state("bullish_momentum")
    assert "空方壓力較明顯" in describe_momentum_state("bearish_momentum")
    assert "大致中性" in describe_momentum_state("neutral")


def test_theme_prompt_requires_one_ml_reference_section():
    assert "只能有一個「ML Reference」段落" in LLM_ANALYST_SYSTEM_PROMPT
    assert "不要另外建立「ML 訊號與風險」" in LLM_ANALYST_SYSTEM_PROMPT
