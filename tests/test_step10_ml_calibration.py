import json

from ml_monitoring import build_calibration_report, build_calibration_summary_markdown
from scripts import build_ml_calibration_report as script


def make_outcome(
    *,
    horizon=5,
    probability=0.65,
    actual_up=True,
    large_drop_risk=None,
    actual_max_drop=-0.03,
):
    return {
        "ticker": "MU",
        "prediction_date": "2026-06-30",
        "horizon_trading_days": horizon,
        "predicted_up_probability": probability,
        "actual_up": actual_up,
        "predicted_large_drop_risk": large_drop_risk,
        "actual_max_drop_pct": actual_max_drop,
        "outcome_status": "computed",
    }


def test_build_calibration_report_buckets_upside_probabilities():
    outcomes = [
        make_outcome(horizon=5, probability=0.61, actual_up=True),
        make_outcome(horizon=5, probability=0.69, actual_up=False),
        make_outcome(horizon=5, probability=0.82, actual_up=True),
    ]

    report = build_calibration_report(
        outcomes,
        bucket_count=10,
        thresholds={
            "min_usable_sample_size": 0,
            "max_mean_absolute_calibration_error": 1.0,
            "max_calibration_error": 1.0,
        },
    )

    up_5d = report["targets"]["up_5d"]
    bucket_06 = next(bucket for bucket in up_5d["buckets"] if bucket["bucket"] == "0.6-0.7")

    assert up_5d["usable_sample_size"] == 3
    assert bucket_06["sample_size"] == 2
    assert bucket_06["avg_predicted_probability"] == 0.65
    assert bucket_06["actual_rate"] == 0.5
    assert bucket_06["calibration_error"] == -0.15
    assert report["warnings"] == []


def test_build_calibration_report_checks_large_drop_risk():
    outcomes = [
        make_outcome(
            horizon=20,
            probability=0.4,
            actual_up=True,
            large_drop_risk=0.72,
            actual_max_drop=-0.10,
        ),
        make_outcome(
            horizon=20,
            probability=0.6,
            actual_up=False,
            large_drop_risk=0.78,
            actual_max_drop=-0.02,
        ),
    ]

    report = build_calibration_report(
        outcomes,
        bucket_count=10,
        thresholds={"min_usable_sample_size": 1},
    )

    large_drop = report["targets"]["large_drop_20d"]
    bucket_07 = next(bucket for bucket in large_drop["buckets"] if bucket["bucket"] == "0.7-0.8")

    assert large_drop["usable_sample_size"] == 2
    assert bucket_07["sample_size"] == 2
    assert bucket_07["actual_rate"] == 0.5
    assert bucket_07["avg_predicted_probability"] == 0.75
    assert bucket_07["calibration_error"] == -0.25


def test_build_calibration_report_warns_when_error_is_high():
    outcomes = [
        make_outcome(horizon=10, probability=0.9, actual_up=False),
        make_outcome(horizon=10, probability=0.8, actual_up=False),
    ]

    report = build_calibration_report(
        outcomes,
        thresholds={
            "min_usable_sample_size": 1,
            "max_mean_absolute_calibration_error": 0.10,
            "max_calibration_error": 0.20,
        },
    )

    warning_metrics = {warning["metric"] for warning in report["warnings"]}
    assert "mean_absolute_calibration_error" in warning_metrics
    assert "max_calibration_error" in warning_metrics
    assert report["alert"]["should_alert"] is True


def test_build_calibration_summary_markdown_lists_targets_and_buckets():
    report = build_calibration_report(
        [make_outcome(horizon=5, probability=0.65, actual_up=True)],
        thresholds={"min_usable_sample_size": 1},
    )

    markdown = build_calibration_summary_markdown(report)

    assert "# ML Calibration Report" in markdown
    assert "| Target | Usable Sample |" in markdown
    assert "### up_5d" in markdown
    assert "0.6-0.7" in markdown


def test_build_ml_calibration_script_writes_json_and_markdown(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "fetch_ml_prediction_outcomes_for_metrics",
        lambda universe, model_version, days, limit: [
            make_outcome(horizon=5, probability=0.65, actual_up=True)
        ],
    )

    result = script.main(["--output-dir", str(tmp_path), "--days", "30"])

    output = capsys.readouterr().out
    json_path = tmp_path / "ml_calibration_report_all_models_30d_v1.json"
    markdown_path = tmp_path / "ml_calibration_summary_all_models_30d_v1.md"

    assert result == 0
    assert "outcomes=1" in output
    assert json_path.exists()
    assert markdown_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["window_days"] == 30
