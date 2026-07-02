import json
from datetime import UTC, datetime

from ml_monitoring import (
    build_model_acceptance_email_summary,
    build_model_acceptance_report,
    build_model_acceptance_summary_markdown,
)
from scripts import build_ml_model_upgrade_review as script


def make_metrics(*, accuracy=0.58, brier=0.21, large_drop_hit_rate=0.62, sample_size=100):
    return {
        "model_version": "model_v1",
        "horizons": {
            str(horizon): {
                "sample_size": sample_size,
                "up_accuracy": accuracy,
                "brier_score": brier,
                "large_drop_hit_rate": large_drop_hit_rate if horizon == 20 else None,
            }
            for horizon in (5, 10, 20)
        },
    }


def make_calibration(warnings=None):
    return {
        "model_version": "candidate_v1",
        "warnings": warnings or [],
    }


def make_drift(warnings=None):
    return {
        "warnings": warnings or [],
    }


def test_model_upgrade_review_promotes_clean_candidate():
    production = make_metrics(accuracy=0.55, brier=0.22, large_drop_hit_rate=0.60)
    candidate = make_metrics(accuracy=0.58, brier=0.21, large_drop_hit_rate=0.62)

    report = build_model_acceptance_report(
        production_metrics=production,
        candidate_metrics=candidate,
        candidate_calibration=make_calibration(),
        drift_report=make_drift(),
        candidate_model_version="candidate_v1",
        production_model_version="production_v1",
        generated_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert report["recommendation"] == "promote"
    assert report["alert"]["should_alert"] is True
    assert all(check["status"] == "pass" for check in report["checks"])


def test_model_upgrade_review_rejects_candidate_with_worse_accuracy():
    production = make_metrics(accuracy=0.58, brier=0.22, large_drop_hit_rate=0.60)
    candidate = make_metrics(accuracy=0.54, brier=0.21, large_drop_hit_rate=0.62)

    report = build_model_acceptance_report(
        production_metrics=production,
        candidate_metrics=candidate,
        candidate_calibration=make_calibration(),
        drift_report=make_drift(),
    )

    assert report["recommendation"] == "reject"
    assert any(check["name"] == "up_accuracy_5d" for check in report["checks"])


def test_model_upgrade_review_flags_manual_review_for_drift_warning():
    production = make_metrics()
    candidate = make_metrics(accuracy=0.59, brier=0.20, large_drop_hit_rate=0.63)

    report = build_model_acceptance_report(
        production_metrics=production,
        candidate_metrics=candidate,
        candidate_calibration=make_calibration(),
        drift_report=make_drift(
            [
                {
                    "source": "feature_drift",
                    "metric": "rsi_14",
                    "message": "Feature drift detected.",
                }
            ]
        ),
    )

    assert report["recommendation"] == "manual_review"
    assert any(check["name"] == "drift_warning" for check in report["checks"])


def test_model_upgrade_review_skips_when_candidate_is_missing():
    report = build_model_acceptance_report(production_metrics=make_metrics())

    assert report["recommendation"] == "no_candidate"
    assert report["alert"]["should_alert"] is False


def test_model_upgrade_review_markdown_and_email_summary_are_readable():
    report = build_model_acceptance_report(
        production_metrics=make_metrics(),
        candidate_metrics=make_metrics(accuracy=0.54),
        candidate_calibration=make_calibration(),
        drift_report=make_drift(),
    )

    markdown = build_model_acceptance_summary_markdown(report)
    email_summary = build_model_acceptance_email_summary(report)

    assert "# ML Model Upgrade Review" in markdown
    assert "Recommendation" in markdown
    assert "Model upgrade review recommendation" in email_summary


def test_build_model_upgrade_review_script_writes_reports_and_dry_run_alert(tmp_path, capsys):
    production_path = tmp_path / "production.json"
    candidate_path = tmp_path / "candidate.json"
    calibration_path = tmp_path / "calibration.json"
    drift_path = tmp_path / "drift.json"
    production_path.write_text(json.dumps(make_metrics()), encoding="utf-8")
    candidate_path.write_text(json.dumps(make_metrics(accuracy=0.54)), encoding="utf-8")
    calibration_path.write_text(json.dumps(make_calibration()), encoding="utf-8")
    drift_path.write_text(json.dumps(make_drift()), encoding="utf-8")

    exit_code = script.main(
        [
            "--production-metrics-path",
            str(production_path),
            "--candidate-metrics-path",
            str(candidate_path),
            "--candidate-calibration-path",
            str(calibration_path),
            "--drift-path",
            str(drift_path),
            "--production-model-version",
            "production_v1",
            "--candidate-model-version",
            "candidate_v1",
            "--output-dir",
            str(tmp_path),
            "--send-alert",
            "--dry-run-alert",
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "recommendation=reject" in captured
    assert "alert_status=dry_run" in captured
    assert (tmp_path / "ml_model_upgrade_review_production_v1_vs_candidate_v1_v1.json").exists()
    assert (tmp_path / "ml_model_upgrade_review_production_v1_vs_candidate_v1_v1.md").exists()
