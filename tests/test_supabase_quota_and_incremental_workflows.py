import json
from datetime import date
from pathlib import Path

from data_providers.price_history import (
    build_incremental_price_ingest_plan,
    classify_price_history_status,
)
from data_store.supabase_store import fetch_daily_prices
from maintenance.diagnostics import build_pipeline_diagnosis
from scripts.check_supabase_access import classify_http_failure
from scripts.refresh_ml_training_dataset import merge_rows
from scripts.send_pipeline_alert import add_preflight_failure_context


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        return json.dumps(self.rows).encode("utf-8")


def test_fetch_daily_prices_supports_recent_filtered_window():
    calls = []

    def fake_open_url(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(
            [
                {"date": "2026-08-19"},
                {"date": "2026-08-18"},
            ]
        )

    rows = fetch_daily_prices(
        ticker="MU",
        start_date="2026-08-01",
        end_date="2026-08-19",
        recent_limit=2,
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert [row["date"] for row in rows] == ["2026-08-18", "2026-08-19"]
    assert "date=gte.2026-08-01" in calls[0]
    assert "date=lte.2026-08-19" in calls[0]
    assert "order=date.desc" in calls[0]
    assert "limit=2" in calls[0]


def test_incremental_price_plan_uses_overlap_and_skips_history_warning():
    plan = build_incremental_price_ingest_plan(
        latest_date=date(2026, 8, 18),
        data_end_date=date(2026, 8, 20),
        overlap_days=10,
    )

    assert plan.fetch_start_date == date(2026, 8, 8)
    assert plan.incremental is True
    assert (
        classify_price_history_status(
            first_date=date(2026, 8, 10),
            trading_days_in_research_window=7,
            plan=plan,
        )
        == "success"
    )


def test_supabase_quota_is_classified_before_generic_connection_failure():
    message = (
        "Supabase preflight failed with HTTP 402: "
        '{"code":"exceed_egress_quota","message":"Service for this project is restricted"}'
    )
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-prices",
        workflow_status="failed",
        sources=[
            {
                "status": "failed",
                "errors": [
                    {
                        "step": "supabase_preflight",
                        "status": "failed",
                        "message": message,
                    }
                ],
            }
        ],
    )

    assert diagnosis["findings"][0]["category"] == "supabase_quota"
    assert classify_http_failure(402, message) == "supabase_quota"


def test_recent_dataset_rows_replace_matching_weekly_rows():
    merged = merge_rows(
        [
            {"ticker": "MU", "date": "2026-07-01", "value": "old"},
            {"ticker": "AAPL", "date": "2026-07-01", "value": "keep"},
        ],
        [{"ticker": "MU", "date": "2026-07-01", "value": "new"}],
    )

    assert len(merged) == 2
    assert next(row for row in merged if row["ticker"] == "MU")["value"] == "new"


def test_daily_ml_workflow_restores_weekly_base_and_refreshes_recent_rows():
    workflow = Path(".github/workflows/daily-ml-predictions.yml").read_text(
        encoding="utf-8"
    )

    assert "Restore latest weekly ML dataset" in workflow
    assert "python scripts/refresh_ml_training_dataset.py" in workflow
    assert "python scripts/build_ml_training_dataset.py" not in workflow
    assert "python scripts/check_supabase_access.py" in workflow


def test_failure_email_includes_failed_supabase_preflight(tmp_path, monkeypatch):
    preflight_path = tmp_path / "data" / "maintenance" / "supabase_preflight.json"
    preflight_path.parent.mkdir(parents=True)
    preflight_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "errors": [
                    {
                        "message": "Supabase preflight failed with HTTP 402: exceed_egress_quota"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.send_pipeline_alert.PROJECT_ROOT", tmp_path)

    message = add_preflight_failure_context("Daily prices workflow failed.")

    assert "exceed_egress_quota" in message
