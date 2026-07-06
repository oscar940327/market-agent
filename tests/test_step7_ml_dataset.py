import csv
import json

import pytest

from data_store.supabase_store import (
    fetch_market_regimes,
    fetch_news_events_for_dataset,
    fetch_similar_case_results,
    fetch_technical_features,
)
from ml_dataset import build_training_dataset, write_dataset_outputs


def make_price_rows(periods=320):
    rows = []
    current = 100.0
    for index in range(periods):
        rows.append(
            {
                "date": f"2022-01-{index + 1:02d}" if index < 28 else None,
                "close": current,
                "volume": 1000.0 + index,
            }
        )
        current += 1.0

    # Use simple valid ISO dates without bringing pandas into this test.
    from datetime import date, timedelta

    start = date(2022, 1, 3)
    for index, row in enumerate(rows):
        row["date"] = (start + timedelta(days=index)).isoformat()
    return rows


def make_technical_rows(price_rows):
    rows = []
    for index, price_row in enumerate(price_rows):
        close = float(price_row["close"])
        rows.append(
            {
                "ticker": "MU",
                "date": price_row["date"],
                "close": close,
                "volume": price_row["volume"],
                "ma5": close - 2,
                "ma10": close - 4,
                "ma20": close - 8,
                "ma50": close - 20,
                "ma200": close - 50,
                "rsi_14": 60.0,
                "macd": 2.0,
                "macd_histogram": 0.5,
                "is_breakout": index == 220,
                "is_volume_surge": index == 220,
                "is_pullback": False,
            }
        )
    return rows


def make_market_rows(price_rows):
    rows = []
    for index, price_row in enumerate(price_rows):
        close = 300.0 + index
        rows.append(
            {
                "date": price_row["date"],
                "benchmark": "QQQ",
                "regime": "bull",
                "close": close,
                "ma200": close - 10,
                "regime_changed": index == 200,
            }
        )
    return rows


def test_build_training_dataset_joins_features_and_labels():
    price_rows = make_price_rows()
    technical_rows = make_technical_rows(price_rows)
    market_rows = make_market_rows(price_rows)

    result = build_training_dataset(
        tickers=["MU"],
        daily_price_rows_by_ticker={"MU": price_rows},
        technical_rows_by_ticker={"MU": technical_rows},
        market_regime_rows=market_rows,
        news_event_rows_by_ticker={
            "MU": [
                {
                    "published_at": "2022-08-03T12:00:00+00:00",
                    "sentiment": "positive",
                    "topic": "earnings_guidance",
                    "importance": "high",
                },
                {
                    "published_at": "2022-08-08T12:00:00+00:00",
                    "sentiment": "negative",
                    "topic": "risk_event",
                    "importance": "medium",
                },
            ]
        },
        similar_case_rows_by_ticker={
            "MU": [
                {
                    "query_date": "2022-08-11",
                    "sample_size": 42,
                    "win_rate_5d": 0.55,
                    "win_rate_10d": 0.57,
                    "win_rate_20d": 0.6,
                    "average_forward_return_20d": 0.04,
                    "max_loss_20d": -0.08,
                    "evidence_quality": "medium",
                }
            ]
        },
        generated_at="2026-06-29T00:00:00+00:00",
    )

    rows = result["rows"]
    row = next(item for item in rows if item["date"] == "2022-08-11")

    assert row["split"] == "validation"
    assert row["price_vs_ma20"] == pytest.approx(8 / (320 - 8))
    assert row["return_5d"] > 0
    assert row["relative_strength_vs_qqq_20d"] is not None
    assert row["relative_strength_vs_qqq_60d"] is not None
    assert row["drawdown_from_20d_high"] == 0.0
    assert row["drawdown_from_60d_high"] == 0.0
    assert row["ma20_slope_5d"] > 0
    assert row["ma50_slope_10d"] > 0
    assert row["rsi_change_5d"] == 0.0
    assert row["macd_histogram_change_5d"] == 0.0
    assert row["days_above_ma20"] > 0
    assert row["days_below_ma20"] == 0
    assert row["volatility_20d"] >= 0
    assert row["volatility_regime"] in {"low", "normal", "high"}
    assert row["qqq_above_ma200"] is True
    assert row["qqq_return_20d"] > 0
    assert row["news_count_30d"] == 2
    assert row["news_sentiment_score_30d"] == 0.0
    assert row["high_importance_news_count_30d"] == 1
    assert row["risk_event_count_30d"] == 1
    assert row["earnings_guidance_count_30d"] == 1
    assert row["news_missing"] is False
    assert row["similar_case_sample_size"] == 42
    assert row["similar_case_evidence_quality"] == "medium"
    assert row["forward_return_20d"] > 0
    assert row["up_20d"] is True
    assert row["non_upside_20d"] is False
    assert row["large_drop_20d"] is False
    assert row["breakout_success_20d"] is True
    assert result["metadata"]["validation_count"] == len(rows)
    assert result["metadata"]["excluded_row_reason_summary"]["missing_market_regime"] > 0
    assert result["metadata"]["excluded_row_reason_summary"]["missing_forward_labels"] == 20


def test_training_dataset_keeps_rows_when_news_and_similar_cases_are_missing():
    price_rows = make_price_rows()
    result = build_training_dataset(
        tickers=["MU"],
        daily_price_rows_by_ticker={"MU": price_rows},
        technical_rows_by_ticker={"MU": make_technical_rows(price_rows)},
        market_regime_rows=make_market_rows(price_rows),
    )

    row = result["rows"][0]

    assert row["news_missing"] is True
    assert row["news_count_30d"] == 0
    assert row["similar_case_sample_size"] == 0
    assert row["similar_case_evidence_quality"] == "none"


def test_write_dataset_outputs(tmp_path):
    price_rows = make_price_rows()
    result = build_training_dataset(
        tickers=["MU"],
        daily_price_rows_by_ticker={"MU": price_rows},
        technical_rows_by_ticker={"MU": make_technical_rows(price_rows)},
        market_regime_rows=make_market_rows(price_rows),
        generated_at="2026-06-29T00:00:00+00:00",
    )
    csv_path = tmp_path / "dataset.csv"
    metadata_path = tmp_path / "metadata.json"

    write_dataset_outputs(
        rows=result["rows"],
        metadata=result["metadata"],
        csv_path=csv_path,
        metadata_path=metadata_path,
    )

    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))

    assert csv_rows[0]["ticker"] == "MU"
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["row_count"] == len(
        result["rows"]
    )


def test_step7_supabase_fetchers_paginate_and_filter_urls():
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
            return FakeResponse([{"date": "2022-01-01"}] * 2)
        return FakeResponse([])

    fetch_technical_features(
        ticker="MU",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
        page_size=2,
    )
    fetch_market_regimes(
        benchmark="QQQ",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
        page_size=2,
    )
    fetch_news_events_for_dataset(
        ticker="MU",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
        page_size=2,
    )
    fetch_similar_case_results(
        ticker="MU",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
        page_size=2,
    )

    assert any("technical_features" in call and "ticker=eq.MU" in call for call in calls)
    assert any("market_regimes" in call and "benchmark=eq.QQQ" in call for call in calls)
    assert any("news_events" in call and "ticker=eq.MU" in call for call in calls)
    assert any(
        "similar_case_results" in call and "query_ticker=eq.MU" in call
        for call in calls
    )
