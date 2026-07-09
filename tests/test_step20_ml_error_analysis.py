import json
from datetime import UTC, datetime

from ml_model_improvement import (
    build_step20_error_analysis_report,
    build_step20_error_analysis_summary_markdown,
)
from scripts import build_step20_ml_error_analysis as script


def make_outcome(
    *,
    ticker="MU",
    horizon=20,
    probability=0.7,
    actual_up=False,
    actual_max_drop=-0.12,
    predicted_max_drop=-0.04,
    market_regime="bull",
    technical_state="bearish",
    news_state="positive",
    risk_state="high",
):
    return {
        "ticker": ticker,
        "prediction_date": "2026-06-30",
        "horizon_trading_days": horizon,
        "actual_up": actual_up,
        "actual_max_drop_pct": actual_max_drop,
        "predicted_up_probability": probability,
        "up_prediction_correct": (probability >= 0.5) == actual_up,
        "outcome_status": "computed",
        "ml_predictions": {
            "model_version": "baseline_v1",
            "feature_version": "ml_features_v1",
            "universe": "QQQ100",
            "predicted_max_drop_20d": predicted_max_drop,
            "feature_snapshot": {
                "market_regime": market_regime,
                "market_snapshot": {
                    "technical_state": technical_state,
                    "news_state": news_state,
                    "risk_state": risk_state,
                },
            },
        },
    }


def test_step20_error_analysis_flags_weak_horizon_and_downside_risk():
    outcomes = [
        make_outcome(ticker="MU", horizon=20, probability=0.8, actual_up=False),
        make_outcome(ticker="MU", horizon=20, probability=0.7, actual_up=False),
        make_outcome(ticker="NVDA", horizon=20, probability=0.4, actual_up=True),
        make_outcome(ticker="NVDA", horizon=5, probability=0.6, actual_up=True),
    ]

    report = build_step20_error_analysis_report(
        outcomes,
        generated_at=datetime(2026, 7, 9, tzinfo=UTC),
        thresholds={"min_group_sample_size": 1},
    )

    assert report["report_version"] == "step20_ml_error_analysis_v1"
    assert report["computed_outcomes"] == 4
    assert report["horizon_summary"]["20"]["up_accuracy"] == 0.0
    assert report["horizon_summary"]["20"]["downside_underestimation_rate"] == 1.0
    assert any(finding["source"] == "downside_risk" for finding in report["findings"])
    assert report["group_breakdowns"]["ticker"]["worst_groups"][0]["value"] in {"MU", "NVDA"}

    markdown = build_step20_error_analysis_summary_markdown(report)
    assert "# Step 20 ML Error Analysis" in markdown
    assert "Downside Underestimation" in markdown


def test_step20_error_analysis_script_writes_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "fetch_ml_prediction_outcomes_for_metrics",
        lambda universe, model_version, days, limit: [make_outcome()],
    )

    exit_code = script.main(
        [
            "--days",
            "90",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "computed_outcomes=1" in captured

    json_path = tmp_path / "step20_ml_error_analysis_v1.json"
    markdown_path = tmp_path / "step20_ml_error_analysis_v1.md"
    assert json_path.exists()
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["computed_outcomes"] == 1
