import json

import pandas as pd
import pytest

from data_store.supabase_store import fetch_daily_prices
from technical_features.calculator import build_technical_feature_records


def make_price_data(periods=220):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=periods),
            "open": [float(index + 1) for index in range(periods)],
            "high": [float(index + 2) for index in range(periods)],
            "low": [float(index) for index in range(periods)],
            "close": [float(index + 1) for index in range(periods)],
            "volume": [1000000.0] * periods,
            "provider": ["yfinance"] * periods,
        }
    )


def test_build_technical_feature_records_outputs_supabase_shape():
    records = build_technical_feature_records(
        ticker="mu",
        price_provider="yfinance",
        price_data=make_price_data(),
    )

    latest = records[-1]

    assert len(records) == 220
    assert latest["ticker"] == "MU"
    assert latest["price_provider"] == "yfinance"
    assert latest["close"] == 220.0
    assert latest["ma5"] == 218.0
    assert latest["ma10"] == 215.5
    assert latest["ma20"] == 210.5
    assert latest["ma50"] == 195.5
    assert latest["ma200"] == 120.5
    assert latest["rsi_14"] == 100.0
    assert latest["drawdown_from_20d_high"] == 0.0
    assert latest["drawdown_from_60d_high"] == 0.0
    assert latest["ma20_slope_5d"] == pytest.approx(5 / 205.5)
    assert latest["ma50_slope_10d"] == pytest.approx(10 / 185.5)
    assert latest["rsi_change_5d"] == 0.0
    assert latest["macd_histogram_change_5d"] is not None
    assert latest["days_above_ma20"] == 201
    assert latest["days_below_ma20"] == 0
    assert latest["volume_trend_20d"] == 0.0
    assert latest["volatility_regime"] == "low"
    assert latest["short_term_trend"] == "strong"
    assert latest["feature_version"] == "v1"
    assert latest["computed_at"]


def test_early_rows_keep_nullable_moving_averages():
    records = build_technical_feature_records(
        ticker="MU",
        price_provider="yfinance",
        price_data=make_price_data(periods=4),
    )

    latest = records[-1]

    assert latest["ma5"] is None
    assert latest["ma10"] is None
    assert latest["ma20"] is None
    assert latest["ma50"] is None
    assert latest["drawdown_from_20d_high"] is None
    assert latest["days_above_ma20"] == 0
    assert latest["days_below_ma20"] == 0
    assert latest["volatility_regime"] == "unknown"
    assert latest["short_term_trend"] == "unknown"
    assert latest["is_breakout"] is False


def test_breakout_and_volume_surge_can_be_detected():
    price_data = make_price_data(periods=25)
    price_data.loc[24, "close"] = 100.0
    price_data.loc[24, "volume"] = 3000000.0

    records = build_technical_feature_records(
        ticker="MU",
        price_provider="yfinance",
        price_data=price_data,
    )

    latest = records[-1]

    assert latest["is_breakout"] is True
    assert latest["is_volume_surge"] is True


def test_empty_price_data_returns_no_records():
    assert (
        build_technical_feature_records(
            ticker="MU",
            price_provider="yfinance",
            price_data=pd.DataFrame(),
        )
        == []
    )


def test_fetch_daily_prices_paginates_supabase_rows():
    calls = []

    class FakeResponse:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return json.dumps(self.rows).encode("utf-8")

    def fake_open_url(request, timeout):
        calls.append(request.full_url)
        if "offset=0" in request.full_url:
            return FakeResponse([{"date": "2026-01-01"}] * 2)
        return FakeResponse([{"date": "2026-01-03"}])

    rows = fetch_daily_prices(
        ticker="MU",
        provider="yfinance",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
        page_size=2,
    )

    assert len(rows) == 3
    assert len(calls) == 2
