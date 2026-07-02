import json
from datetime import UTC, datetime

from ml_monitoring import (
    build_ml_health_email_summary,
    build_ml_health_report,
    build_ml_health_summary_markdown,
)
from scripts import build_ml_health_report as script


def make_metrics(warnings=None, computed_outcomes=100):
    return {
        "report_version": "ml_monitoring_metrics_v1",
        "computed_outcomes": computed_outcomes,
        "warnings": warnings or [],
    }


def make_calibration(warnings=None):
    return {
        "report_version": "ml_calibration_report_v1",
        "warnings": warnings or [],
    }


def make_drift(warnings=None):
    return {
        "report_version": "ml_drift_report_v1",
        "recent_rows": 30,
        "baseline_rows": 365,
        "warnings": warnings or [],
    }


def make_upgrade(recommendation="no_candidate", checks=None):
    return {
        "report_version": "ml_model_upgrade_review_v1",
        "recommendation": recommendation,
        "checks": checks or [],
    }


def test_ml_health_report_is_healthy_when_all_components_are_clean():
    report = build_ml_health_report(
        metrics_report=make_metrics(),
        calibration_report=make_calibration(),
        drift_report=make_drift(),
        model_upgrade_report=make_upgrade(),
        generated_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert report["overall_status"] == "healthy"
    assert report["ml_reference_policy"]["status"] == "normal"
    assert report["alert"]["should_alert"] is False


def test_ml_health_report_degrades_for_drift_warning():
    report = build_ml_health_report(
        metrics_report=make_metrics(),
        calibration_report=make_calibration(),
        drift_report=make_drift(
            [
                {
                    "source": "feature_drift",
                    "status": "warning",
                    "metric": "rsi_14",
                    "message": "Feature drift detected.",
                }
            ]
        ),
        model_upgrade_report=make_upgrade(),
    )

    assert report["overall_status"] == "degraded"
    assert report["ml_reference_policy"]["status"] == "reduced_trust"
    assert report["alert"]["should_alert"] is True
    assert "Review feature" in report["action_needed"][0]


def test_ml_health_report_warns_for_model_upgrade_manual_review():
    report = build_ml_health_report(
        metrics_report=make_metrics(),
        calibration_report=make_calibration(),
        drift_report=make_drift(),
        model_upgrade_report=make_upgrade(
            recommendation="manual_review",
            checks=[
                {
                    "name": "sample_size_5d",
                    "status": "manual_review",
                    "message": "Sample size is low.",
                }
            ],
        ),
    )

    assert report["overall_status"] == "warning"
    assert report["alert"]["severity"] == "warning"
    assert any(warning["source"] == "model_upgrade" for warning in report["warnings"])


def test_ml_health_report_marks_missing_reports_unknown_and_alertable():
    report = build_ml_health_report(metrics_report=make_metrics())

    assert report["overall_status"] == "unknown"
    assert report["ml_reference_policy"]["status"] == "unavailable"
    assert report["alert"]["should_alert"] is True


def test_ml_health_summary_markdown_and_email_summary_are_readable():
    report = build_ml_health_report(
        metrics_report=make_metrics(),
        calibration_report=make_calibration(),
        drift_report=make_drift(),
        model_upgrade_report=make_upgrade(),
    )

    markdown = build_ml_health_summary_markdown(report)
    email_summary = build_ml_health_email_summary(report)

    assert "# ML Health Report" in markdown
    assert "ML Reference policy" in markdown
    assert "ML health status" in email_summary


def test_build_ml_health_report_script_writes_reports_and_dry_run_alert(tmp_path, capsys):
    metrics_path = tmp_path / "ml_metrics_report_all_models_90d_v1.json"
    calibration_path = tmp_path / "ml_calibration_report_all_models_90d_v1.json"
    drift_path = tmp_path / "ml_drift_report_30d_vs_365d_v1.json"
    upgrade_path = tmp_path / "ml_model_upgrade_review_production_vs_candidate_v1.json"
    metrics_path.write_text(json.dumps(make_metrics()), encoding="utf-8")
    calibration_path.write_text(json.dumps(make_calibration()), encoding="utf-8")
    drift_path.write_text(
        json.dumps(
            make_drift(
                [
                    {
                        "source": "feature_drift",
                        "status": "warning",
                        "metric": "rsi_14",
                        "message": "Feature drift detected.",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    upgrade_path.write_text(json.dumps(make_upgrade()), encoding="utf-8")

    exit_code = script.main(
        [
            "--output-dir",
            str(tmp_path),
            "--send-alert",
            "--dry-run-alert",
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "overall_status=degraded" in captured
    assert "alert_status=dry_run" in captured
    assert (tmp_path / "ml_health_report_v1.json").exists()
    assert (tmp_path / "ml_health_summary_v1.md").exists()
