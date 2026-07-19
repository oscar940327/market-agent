import json

from data_store.supabase_store import fetch_ml_prediction_outcomes_for_metrics
from ml_monitoring import (
    build_monitoring_metrics_report,
    build_monitoring_summary_markdown,
)
from scripts import build_ml_monitoring_metrics as script


def make_outcome(
    *,
    horizon=5,
    actual_up=True,
    probability=0.6,
    return_error=0.01,
    actual_max_drop=-0.03,
    large_drop_risk=None,
    large_drop_correct=None,
    predicted_max_drop=-0.04,
):
    return {
        "ticker": "MU",
        "prediction_date": "2026-06-30",
        "horizon_trading_days": horizon,
        "actual_return_pct": 0.05 if actual_up else -0.05,
        "actual_up": actual_up,
        "actual_max_drop_pct": actual_max_drop,
        "actual_max_runup_pct": 0.08,
        "predicted_up_probability": probability,
        "predicted_large_drop_risk": large_drop_risk,
        "up_prediction_correct": (probability >= 0.5) == actual_up,
        "large_drop_prediction_correct": large_drop_correct,
        "return_error": return_error,
        "outcome_status": "computed",
        "ml_predictions": {
            "model_version": "daily_prediction_v1",
            "feature_version": "ml_features_v1",
            "universe": "QQQ100",
            "predicted_max_drop_20d": predicted_max_drop,
        },
    }


def test_build_monitoring_metrics_report_calculates_core_metrics():
    outcomes = [
        make_outcome(horizon=5, actual_up=True, probability=0.7, return_error=0.02),
        make_outcome(horizon=5, actual_up=False, probability=0.6, return_error=-0.03),
        make_outcome(horizon=5, actual_up=False, probability=0.3, return_error=0.01),
        make_outcome(
            horizon=20,
            actual_up=False,
            probability=0.4,
            actual_max_drop=-0.12,
            large_drop_risk=0.7,
            large_drop_correct=True,
            return_error=-0.04,
            predicted_max_drop=-0.04,
        ),
        make_outcome(
            horizon=20,
            actual_up=True,
            probability=0.7,
            actual_max_drop=-0.03,
            large_drop_risk=0.2,
            large_drop_correct=True,
            return_error=0.02,
            predicted_max_drop=-0.04,
        ),
    ]

    report = build_monitoring_metrics_report(
        outcomes,
        days=90,
        universe="QQQ100",
        model_version="daily_prediction_v1",
        thresholds={"min_sample_size": 1},
    )

    horizon_5 = report["horizons"]["5"]
    horizon_20 = report["horizons"]["20"]

    assert horizon_5["sample_size"] == 3
    assert horizon_5["up_accuracy"] == 0.666667
    assert horizon_5["precision"] == 0.5
    assert horizon_5["recall"] == 1.0
    assert horizon_5["return_mae"] == 0.02
    assert horizon_20["large_drop_accuracy"] == 1.0
    assert horizon_20["large_drop_hit_rate"] == 1.0
    assert horizon_20["downside_underestimation_rate"] == 0.5
    assert report["alert"]["should_alert"] is True


def test_build_monitoring_metrics_report_warns_for_small_sample_and_low_accuracy():
    outcomes = [
        make_outcome(horizon=5, actual_up=True, probability=0.3, return_error=0.01),
    ]

    report = build_monitoring_metrics_report(outcomes, thresholds={"min_sample_size": 50})

    warning_metrics = {warning["metric"] for warning in report["warnings"]}
    assert "sample_size" in warning_metrics
    assert "up_accuracy" in warning_metrics


def test_build_monitoring_metrics_report_warns_when_auc_is_below_random():
    outcomes = [
        make_outcome(horizon=20, actual_up=True, probability=0.2),
        make_outcome(horizon=20, actual_up=True, probability=0.3),
        make_outcome(horizon=20, actual_up=False, probability=0.7),
        make_outcome(horizon=20, actual_up=False, probability=0.8),
    ]

    report = build_monitoring_metrics_report(
        outcomes,
        thresholds={"min_sample_size": 1, "min_up_accuracy": 0.0},
    )

    warning_metrics = {warning["metric"] for warning in report["warnings"]}
    assert report["horizons"]["20"]["roc_auc"] == 0.0
    assert "roc_auc" in warning_metrics


def test_build_monitoring_metrics_report_does_not_warn_without_computed_outcomes():
    report = build_monitoring_metrics_report([], thresholds={"min_sample_size": 50})

    assert report["data_status"] == "no_computed_outcomes"
    assert report["computed_outcomes"] == 0
    assert report["warnings"] == []
    assert report["alert"]["should_alert"] is False
    assert report["alert"]["reason"] == "no_computed_outcomes"


def test_build_monitoring_summary_markdown_includes_table_and_warnings():
    report = build_monitoring_metrics_report(
        [make_outcome(horizon=5)],
        thresholds={"min_sample_size": 50},
    )

    markdown = build_monitoring_summary_markdown(report)

    assert "# ML Monitoring Metrics" in markdown
    assert "| Horizon | Sample | Up Accuracy |" in markdown
    assert "Warnings" in markdown


def test_fetch_ml_prediction_outcomes_for_metrics_queries_joined_prediction_fields():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'[{"id":"outcome-1"}]'

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    rows = fetch_ml_prediction_outcomes_for_metrics(
        universe="QQQ100",
        model_version="daily_prediction_v1",
        days=90,
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert rows == [{"id": "outcome-1"}]
    assert "ml_prediction_outcomes?select=" in captured["url"]
    assert "outcome_status=eq.computed" in captured["url"]
    assert "ml_predictions.universe=eq.QQQ100" in captured["url"]
    assert "ml_predictions.model_version=eq.daily_prediction_v1" in captured["url"]


def test_build_ml_monitoring_metrics_script_writes_json_and_markdown(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "fetch_ml_prediction_outcomes_for_metrics",
        lambda universe, model_version, days, limit: [make_outcome(horizon=5)],
    )

    result = script.main(["--output-dir", str(tmp_path), "--days", "30"])

    output = capsys.readouterr().out
    json_path = tmp_path / "ml_metrics_report_all_models_30d_v1.json"
    markdown_path = tmp_path / "ml_metrics_summary_all_models_30d_v1.md"

    assert result == 0
    assert "outcomes=1" in output
    assert json_path.exists()
    assert markdown_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["window_days"] == 30
