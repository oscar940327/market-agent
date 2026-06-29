import pandas as pd

from research_logging import (
    build_outcome_updates,
    build_pending_outcome_rows,
    build_research_log_row,
)


def test_build_research_log_row_from_single_stock_data():
    data = {
        "ticker": "mu",
        "evidence_quality": "medium",
        "technical_analysis": {"current_price": 100.0, "data_as_of": "2026-06-26"},
        "research_profile": {
            "price_plan": {
                "decision": "wait_for_better_price",
                "reference_price": 100.0,
            }
        },
    }

    row = build_research_log_row(
        query="MU 現在適合進場嗎",
        intent="single_stock_analysis",
        data=data,
        report="研究摘要\n這是一段很長的報告",
        request_options={"include_news": True},
    )

    assert row["query"] == "MU 現在適合進場嗎"
    assert row["intent"] == "single_stock_analysis"
    assert row["ticker"] == "MU"
    assert row["decision"] == "wait_for_better_price"
    assert row["evidence_quality"] == "medium"
    assert row["price_at_query"] == 100.0
    assert row["data_as_of"] == "2026-06-26"
    assert row["request_options"] == {"include_news": True}


def test_build_pending_outcome_rows_creates_5_10_20_trading_day_placeholders():
    rows = build_pending_outcome_rows(
        research_log_id="log-1",
        ticker="mu",
        query_date=pd.Timestamp("2026-06-01").date(),
        price_at_query=100.0,
    )

    assert [row["horizon_trading_days"] for row in rows] == [5, 10, 20]
    assert {row["outcome_status"] for row in rows} == {"pending"}
    assert {row["used_for_calibration"] for row in rows} == {False}
    assert rows[0]["ticker"] == "MU"


def test_build_outcome_updates_uses_trading_day_offsets_and_risk_path():
    pending = [
        {
            "research_log_id": "log-1",
            "ticker": "MU",
            "query_date": "2026-01-01",
            "horizon_trading_days": 5,
            "price_at_query": 100.0,
            "price_provider": "yfinance",
        }
    ]
    prices = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=6),
            "close": [100.0, 98.0, 102.0, 99.0, 103.0, 105.0],
        }
    )

    updates = build_outcome_updates(pending_outcomes=pending, price_data=prices)
    update = updates[0]

    assert update["outcome_status"] == "computed"
    assert update["actual_date"] == "2026-01-08"
    assert update["price_at_horizon"] == 105.0
    assert update["return_pct"] == 0.05
    assert update["max_drawdown_pct"] == -0.02
    assert update["max_runup_pct"] == 0.05
    assert update["used_for_calibration"] is False


def test_build_outcome_updates_keeps_pending_when_horizon_not_reached():
    pending = [
        {
            "research_log_id": "log-1",
            "ticker": "MU",
            "query_date": "2026-01-01",
            "horizon_trading_days": 20,
            "price_at_query": 100.0,
            "price_provider": "yfinance",
        }
    ]
    prices = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=6),
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        }
    )

    updates = build_outcome_updates(pending_outcomes=pending, price_data=prices)

    assert updates[0]["outcome_status"] == "pending"
    assert updates[0]["computed_at"] is None


def test_build_outcome_updates_marks_missing_price_when_no_prices():
    pending = [
        {
            "research_log_id": "log-1",
            "ticker": "MU",
            "query_date": "2026-01-01",
            "horizon_trading_days": 5,
            "price_at_query": 100.0,
            "price_provider": "yfinance",
        }
    ]

    updates = build_outcome_updates(
        pending_outcomes=pending,
        price_data=pd.DataFrame(),
    )

    assert updates[0]["outcome_status"] == "missing_price"
    assert updates[0]["used_for_calibration"] is False
