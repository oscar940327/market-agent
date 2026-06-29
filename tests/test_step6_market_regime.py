import json
from datetime import date

import pandas as pd

from data_store.supabase_store import fetch_latest_date
from market_regime.calculator import (
    build_market_regime_records,
    classify_market_regime,
)
from market_regime.freshness import build_freshness_report


def make_price_data(periods=260):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2025-01-01", periods=periods),
            "close": [float(index + 1) for index in range(periods)],
        }
    )


def test_market_regime_classification_rules():
    assert classify_market_regime(close=120, ma200=100, three_month_return=0.05) == "bull"
    assert classify_market_regime(close=80, ma200=100, three_month_return=-0.05) == "bear"
    assert (
        classify_market_regime(close=120, ma200=100, three_month_return=-0.05)
        == "sideways"
    )
    assert classify_market_regime(close=120, ma200=None, three_month_return=0.05) == "unknown"


def test_build_market_regime_records_outputs_schema_shape():
    records = build_market_regime_records(
        benchmark="qqq",
        price_data=make_price_data(),
    )
    latest = records[-1]

    assert len(records) == 260
    assert latest["benchmark"] == "QQQ"
    assert latest["ma200"] is not None
    assert latest["three_month_return"] is not None
    assert latest["regime"] == "bull"
    assert latest["rule_version"] == "v1"
    assert latest["data_as_of"] == records[-1]["date"]


def test_freshness_report_marks_dependencies():
    report = build_freshness_report(
        today=date(2026, 6, 27),
        daily_prices_latest_date=date(2026, 6, 26),
        technical_features_latest_date=date(2026, 6, 26),
        market_regimes_latest_date=date(2026, 6, 25),
    )

    assert report["daily_prices"]["status"] == "fresh"
    assert report["technical_features"]["status"] == "fresh"
    assert report["market_regimes"]["status"] == "stale"
    assert report["overall"] == "stale"


def test_fetch_latest_date_returns_latest_row_value():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return json.dumps([{"date": "2026-06-26"}]).encode("utf-8")

    def fake_open_url(request, timeout):
        assert "order=date.desc" in request.full_url
        assert "limit=1" in request.full_url
        assert "ticker=eq.QQQ" in request.full_url
        return FakeResponse()

    latest_date = fetch_latest_date(
        table="daily_prices",
        filters={"ticker": "eq.QQQ"},
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert latest_date == "2026-06-26"
