import json
from datetime import UTC, date, datetime

import data_freshness.service as freshness_service
from data_freshness.service import (
    build_current_data_freshness,
    parse_datetime,
    read_latest_pipeline_run_at,
    read_ml_metadata_generated_at,
)
from market_regime.freshness import (
    build_freshness_report,
    classify_ml_training_freshness,
    classify_news_freshness,
    classify_trading_day_freshness,
    expected_latest_trading_day,
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


def test_expected_latest_trading_day_waits_until_after_market_update_time():
    before_update = expected_latest_trading_day(
        now=datetime(2026, 7, 6, 20, 0, tzinfo=UTC),
    )
    after_update = expected_latest_trading_day(
        now=datetime(2026, 7, 6, 23, 0, tzinfo=UTC),
    )

    assert before_update == date(2026, 7, 2)
    assert after_update == date(2026, 7, 6)


def test_freshness_report_does_not_warn_on_trading_day_before_expected_update():
    report = build_freshness_report(
        today=date(2026, 7, 6),
        now=datetime(2026, 7, 6, 20, 0, tzinfo=UTC),
        daily_prices_latest_date=date(2026, 7, 2),
        technical_features_latest_date=date(2026, 7, 2),
        market_regimes_latest_date=date(2026, 7, 2),
        news_latest_at=datetime(2026, 7, 5, tzinfo=UTC),
        ml_training_generated_at=datetime(2026, 7, 5, tzinfo=UTC),
        pipeline_last_run_at=datetime(2026, 7, 5, 10, tzinfo=UTC),
    )

    assert report["daily_prices"]["status"] == "fresh"
    assert report["daily_prices"]["expected_latest_trading_day"] == "2026-07-02"
    assert report["pipeline_last_run"]["status"] == "fresh"
    assert report["pipeline_last_run"]["reason"] == "waiting_for_expected_market_data_update"
    assert report["overall"] == "fresh"


def test_freshness_report_warns_after_expected_update_time():
    report = build_freshness_report(
        today=date(2026, 7, 6),
        now=datetime(2026, 7, 6, 23, 0, tzinfo=UTC),
        daily_prices_latest_date=date(2026, 7, 2),
        technical_features_latest_date=date(2026, 7, 2),
        market_regimes_latest_date=date(2026, 7, 2),
        news_latest_at=datetime(2026, 7, 5, tzinfo=UTC),
        ml_training_generated_at=datetime(2026, 7, 5, tzinfo=UTC),
        pipeline_last_run_at=datetime(2026, 7, 5, 10, tzinfo=UTC),
    )

    assert report["daily_prices"]["status"] == "warning"
    assert report["daily_prices"]["expected_latest_trading_day"] == "2026-07-06"
    assert report["overall"] == "warning"


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


def test_current_freshness_prefers_supabase_pipeline_run_over_local_log(tmp_path, monkeypatch):
    metadata_path = tmp_path / "training_dataset_v1_metadata.json"
    metadata_path.write_text(
        json.dumps({"generated_at": "2026-07-02T00:00:00+00:00"}),
        encoding="utf-8",
    )
    log_dir = tmp_path / "pipeline_runs"
    log_dir.mkdir()
    (log_dir / "daily_pipeline_2026-06-30_010101.json").write_text(
        json.dumps({"finished_at": "2026-06-30T01:01:01+00:00"}),
        encoding="utf-8",
    )

    def fake_fetch_latest_date(*, table, date_column="date", filters=None):
        if table == "news_events":
            return "2026-07-03T09:00:00+00:00"
        return "2026-07-02"

    def fake_fetch_latest_pipeline_run(*, pipeline="daily"):
        return {"finished_at": "2026-07-03T10:00:00+00:00"}

    monkeypatch.setattr(freshness_service, "fetch_latest_date", fake_fetch_latest_date)
    monkeypatch.setattr(
        freshness_service,
        "fetch_latest_pipeline_run",
        fake_fetch_latest_pipeline_run,
    )

    report = build_current_data_freshness(
        ticker="MU",
        today=date(2026, 7, 3),
        now=datetime(2026, 7, 3, 12, tzinfo=UTC),
        ml_metadata_path=metadata_path,
        pipeline_log_dir=log_dir,
    )

    assert report["pipeline_last_run"]["status"] == "fresh"
    assert report["pipeline_last_run"]["last_run_at"] == "2026-07-03T10:00:00+00:00"
    assert report["overall"] == "fresh"


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
