import json
from datetime import UTC, date, datetime

import data_freshness.service as freshness_service
from data_recovery import build_data_recovery_report
from data_store.supabase_store import (
    fetch_latest_ml_dataset_metadata,
    upsert_ml_dataset_metadata,
)
from maintenance.diagnostics import build_pipeline_diagnosis
from scripts.build_ml_training_dataset import build_ml_dataset_metadata_record


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_recovery_distinguishes_report_impact_from_maintenance_warning():
    report = build_data_recovery_report(
        freshness={
            "daily_prices": {
                "status": "stale",
                "reason": "latest_date_too_old",
                "message": "daily_prices 已落後 2 個交易日。",
            },
            "ml_training_data": {
                "status": "warning",
                "reason": "ml_training_data_getting_old",
                "message": "ML training dataset 已超過 7 天未更新。",
                "metadata_source": "supabase",
            },
        },
        ticker="MU",
        fundamentals={"status": "success"},
        ml_research={
            "status": "success",
            "source": {
                "type": "saved_daily_prediction",
                "prediction_freshness": "fresh",
            },
        },
    )

    assert report["status"] == "action_recommended"
    assert report["report_impact"] == "usable_with_caution"
    assert report["current_report_finding_count"] == 1
    assert report["maintenance_finding_count"] == 1
    price_finding = next(
        finding for finding in report["findings"] if finding["source"] == "daily_prices"
    )
    assert price_finding["affects_current_report"] is True
    assert "--only prices --tickers MU" in price_finding["recommended_action"]["command"]
    training_finding = next(
        finding
        for finding in report["findings"]
        if finding["source"] == "ml_training_data"
    )
    assert training_finding["affects_current_report"] is False
    assert training_finding["metadata_source"] == "supabase"
    assert report["automatic_recovery_executed"] is False


def test_runtime_ml_fallback_recommends_daily_prediction_without_auto_execution():
    report = build_data_recovery_report(
        freshness={},
        ticker="MU",
        fundamentals={"status": "success"},
        ml_research={
            "status": "success",
            "source": {
                "type": "runtime_fallback",
                "reason": "saved_prediction_not_usable:ready/missing",
            },
        },
    )

    finding = report["findings"][0]
    assert finding["source"] == "ml_predictions"
    assert finding["status"] == "warning"
    assert finding["affects_current_report"] is True
    assert finding["recommended_action"]["id"] == "run_daily_ml_predictions"
    assert finding["recommended_action"]["requires_user_approval"] is True


def test_freshness_prefers_shared_supabase_dataset_metadata(tmp_path, monkeypatch):
    local_metadata = tmp_path / "metadata.json"
    local_metadata.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T00:00:00+00:00",
                "data_end_date": "2026-05-30",
                "row_count": 1,
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch_latest_date(*, table, date_column="date", filters=None):
        if table == "news_events":
            return "2026-07-16T00:00:00+00:00"
        if table == "fundamental_snapshots":
            return "2026-07-16T00:00:00+00:00"
        return "2026-07-16"

    monkeypatch.setattr(freshness_service, "fetch_latest_date", fake_fetch_latest_date)
    monkeypatch.setattr(
        freshness_service,
        "fetch_latest_ml_dataset_metadata",
        lambda **kwargs: {
            "dataset_name": "training_dataset_v1",
            "dataset_version": "training_dataset_v1",
            "generated_at": "2026-07-16T05:00:00+00:00",
            "data_end_date": "2026-07-15",
            "row_count": 333232,
            "workflow_run_id": "123",
        },
    )
    monkeypatch.setattr(
        freshness_service,
        "fetch_latest_pipeline_run",
        lambda **kwargs: {"finished_at": "2026-07-16T23:00:00+00:00"},
    )

    report = freshness_service.build_current_data_freshness(
        ticker="MU",
        today=date(2026, 7, 17),
        now=datetime(2026, 7, 17, 5, tzinfo=UTC),
        ml_metadata_path=local_metadata,
    )

    assert report["ml_training_data"]["status"] == "fresh"
    assert report["ml_training_data"]["metadata_source"] == "supabase"
    assert report["ml_training_data"]["row_count"] == 333232
    assert report["fundamental_snapshots"]["status"] == "fresh"


def test_supabase_dataset_metadata_helpers_use_shared_table():
    requests = []

    def fake_open_url(request, timeout):
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.data.decode("utf-8"))
            return FakeResponse([{**payload, "id": "row-1"}])
        return FakeResponse(
            [
                {
                    "dataset_name": "training_dataset_v1",
                    "generated_at": "2026-07-16T05:00:00+00:00",
                    "status": "success",
                }
            ]
        )

    row = {
        "dataset_name": "training_dataset_v1",
        "dataset_version": "training_dataset_v1",
        "universe": "QQQ100",
        "provider": "yfinance",
        "feature_version": "ml_features_v1",
        "label_version": "ml_labels_v1",
        "generated_at": "2026-07-16T05:00:00+00:00",
        "row_count": 100,
        "status": "success",
        "metadata": {},
    }
    inserted = upsert_ml_dataset_metadata(
        row,
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )
    fetched = fetch_latest_ml_dataset_metadata(
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert inserted["status"] == "success"
    assert fetched["dataset_name"] == "training_dataset_v1"
    assert "on_conflict=dataset_name,universe,provider" in requests[0].full_url
    assert "/ml_dataset_metadata?" in requests[1].full_url


def test_dataset_metadata_record_includes_cross_environment_fields(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "456")
    record = build_ml_dataset_metadata_record(
        metadata={
            "generated_at": "2026-07-16T05:00:00+00:00",
            "data_start_date": "2011-01-01",
            "data_end_date": "2026-07-15",
            "universe": "QQQ100",
            "feature_version": "ml_features_v1",
            "label_version": "ml_labels_v1",
            "row_count": 333232,
        },
        provider="yfinance",
    )

    assert record["workflow_run_id"] == "456"
    assert record["data_end_date"] == "2026-07-15"
    assert record["row_count"] == 333232


def test_recovery_report_is_consumed_by_pipeline_diagnosis():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-prices",
        workflow_status="success",
        sources=[
            {
                "recovery_version": "data_recovery_v1",
                "status": "action_recommended",
                "findings": [
                    {
                        "source": "daily_prices",
                        "status": "stale",
                        "message": "daily_prices 已落後 2 個交易日。",
                        "affects_current_report": True,
                        "recommended_action": {
                            "id": "run_prices_pipeline",
                            "command": "python scripts/run_daily_pipeline.py --only prices --tickers MU",
                            "safe_auto_recovery_candidate": True,
                        },
                    }
                ],
            }
        ],
    )

    assert diagnosis["status"] == "warning"
    assert diagnosis["findings"][0]["category"] == "data_recovery"
    assert diagnosis["findings"][0]["retryable"] is True
    assert "--only prices" in diagnosis["findings"][0]["recommended_action"]
