import json
from datetime import UTC, date, datetime

from data_freshness.service import (
    parse_datetime,
    read_latest_pipeline_run_at,
    read_ml_metadata_generated_at,
)
from market_regime.freshness import (
    build_freshness_report,
    classify_ml_training_freshness,
    classify_news_freshness,
    classify_trading_day_freshness,
    is_nyse_trading_day,
)
from scripts.check_freshness import apply_scope


def test_price_freshness_marks_one_trading_day_as_warning():
    result = classify_trading_day_freshness(
        today=date(2026, 6, 30),
        latest_date=date(2026, 6, 29),
        label="daily_prices",
    )

    assert result["status"] == "warning"
    assert result["business_day_lag"] == 1


def test_price_freshness_ignores_nyse_independence_day_observed():
    result = classify_trading_day_freshness(
        today=date(2026, 7, 3),
        latest_date=date(2026, 7, 2),
        label="daily_prices",
    )

    assert is_nyse_trading_day(date(2026, 7, 3)) is False
    assert result["status"] == "fresh"
    assert result["business_day_lag"] == 0
    assert result["trading_day_lag"] == 0


def test_price_freshness_counts_next_nyse_trading_day_after_holiday():
    result = classify_trading_day_freshness(
        today=date(2026, 7, 6),
        latest_date=date(2026, 7, 2),
        label="daily_prices",
    )

    assert result["status"] == "warning"
    assert result["business_day_lag"] == 1
    assert result["trading_day_lag"] == 1


def test_news_freshness_marks_no_recent_news_as_stale():
    result = classify_news_freshness(
        now=datetime(2026, 6, 30, tzinfo=UTC),
        latest_at=datetime(2026, 5, 1, tzinfo=UTC),
    )

    assert result["status"] == "stale"
    assert result["reason"] == "no_news_in_30_days"
    assert "最近 30 天內沒有新聞" in result["message"]


def test_ml_training_freshness_uses_7_and_14_day_thresholds():
    now = datetime(2026, 6, 30, tzinfo=UTC)

    warning = classify_ml_training_freshness(
        now=now,
        generated_at=datetime(2026, 6, 21, tzinfo=UTC),
    )
    stale = classify_ml_training_freshness(
        now=now,
        generated_at=datetime(2026, 6, 10, tzinfo=UTC),
    )

    assert warning["status"] == "warning"
    assert stale["status"] == "stale"


def test_freshness_report_collects_warning_messages():
    report = build_freshness_report(
        today=date(2026, 6, 30),
        now=datetime(2026, 6, 30, tzinfo=UTC),
        daily_prices_latest_date=date(2026, 6, 29),
        technical_features_latest_date=date(2026, 6, 29),
        market_regimes_latest_date=date(2026, 6, 29),
        news_latest_at=datetime(2026, 6, 1, tzinfo=UTC),
        ml_training_generated_at=datetime(2026, 6, 21, tzinfo=UTC),
        pipeline_last_run_at=datetime(2026, 6, 30, tzinfo=UTC),
    )

    assert report["overall"] == "warning"
    assert any(warning["source"] == "daily_prices" for warning in report["warnings"])
    assert any(
        warning["source"] == "ml_training_data" for warning in report["warnings"]
    )


def test_local_metadata_and_pipeline_log_readers(tmp_path):
    metadata_path = tmp_path / "training_dataset_v1_metadata.json"
    metadata_path.write_text(
        json.dumps({"generated_at": "2026-06-28T18:41:03+00:00"}),
        encoding="utf-8",
    )
    log_dir = tmp_path / "pipeline_runs"
    log_dir.mkdir()
    (log_dir / "daily_pipeline_2026-06-30_010101.json").write_text(
        json.dumps({"finished_at": "2026-06-30T01:01:01+00:00"}),
        encoding="utf-8",
    )

    assert read_ml_metadata_generated_at(metadata_path) == datetime(
        2026,
        6,
        28,
        18,
        41,
        3,
        tzinfo=UTC,
    )
    assert read_latest_pipeline_run_at(log_dir) == datetime(
        2026,
        6,
        30,
        1,
        1,
        1,
        tzinfo=UTC,
    )
    assert parse_datetime("2026-06-30T01:01:01Z") == datetime(
        2026,
        6,
        30,
        1,
        1,
        1,
        tzinfo=UTC,
    )


def test_price_scope_ignores_news_freshness_warning():
    report = {
        "overall": "stale",
        "daily_prices": {"status": "fresh"},
        "technical_features": {"status": "fresh"},
        "market_regimes": {"status": "fresh"},
        "news_events": {"status": "stale"},
        "warnings": [
            {
                "source": "news_events",
                "status": "stale",
                "message": "新聞資料過舊（最近 30 天內沒有新聞）。",
            }
        ],
    }

    scoped = apply_scope(report, "prices")

    assert scoped["overall"] == "fresh"
    assert scoped["warnings"] == []
