import json
from datetime import UTC, datetime

from ml_model_improvement import (
    build_step20_calibration_action_report,
    build_step20_calibration_action_summary_markdown,
)
from scripts import build_step20_calibration_actions as script


def make_outcome(*, horizon=5, probability=0.65, actual_up=True):
    return {
        "ticker": "MU",
        "prediction_date": "2026-06-30",
        "horizon_trading_days": horizon,
        "predicted_up_probability": probability,
        "actual_up": actual_up,
        "actual_max_drop_pct": -0.03,
        "outcome_status": "computed",
    }


def test_step20_calibration_action_report_builds_bucket_adjustments():
    outcomes = [
        make_outcome(horizon=5, probability=0.62, actual_up=True),
        make_outcome(horizon=5, probability=0.68, actual_up=False),
        make_outcome(horizon=5, probability=0.66, actual_up=False),
        make_outcome(horizon=5, probability=0.64, actual_up=True),
        make_outcome(horizon=10, probability=0.45, actual_up=True),
    ]

    report = build_step20_calibration_action_report(
        outcomes,
        generated_at=datetime(2026, 7, 9, tzinfo=UTC),
        thresholds={"min_bucket_sample_size": 2, "large_adjustment_threshold": 0.05},
    )

    up_5d = report["target_actions"]["up_5d"]
    usable = [
        bucket
        for bucket in up_5d["bucket_actions"]
        if bucket["status"] == "usable"
    ]

    assert report["report_version"] == "step20_calibration_action_v1"
    assert usable[0]["bucket"] == "0.6-0.7"
    assert usable[0]["suggested_probability"] == 0.5
    assert usable[0]["display_policy"] == "use_calibrated_probability_with_reduced_trust"
    assert report["findings"]

    markdown = build_step20_calibration_action_summary_markdown(report)
    assert "# Step 20 Calibration Action Report" in markdown
    assert "use_calibrated_probability" in markdown


def test_step20_calibration_action_script_writes_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "fetch_ml_prediction_outcomes_for_metrics",
        lambda universe, model_version, days, limit: [
            make_outcome(horizon=5, probability=0.65, actual_up=True),
            make_outcome(horizon=5, probability=0.66, actual_up=False),
        ],
    )

    exit_code = script.main(
        [
            "--output-dir",
            str(tmp_path),
            "--days",
            "90",
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "computed_outcomes=2" in captured

    json_path = tmp_path / "step20_calibration_action_v1.json"
    markdown_path = tmp_path / "step20_calibration_action_v1.md"
    assert json_path.exists()
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_version"] == "step20_calibration_action_v1"
