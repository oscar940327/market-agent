import json
from datetime import UTC, datetime

from ml_model_improvement import (
    build_step20_improvement_summary_markdown,
    build_step20_improvement_summary_report,
)
from scripts import build_step20_improvement_summary as script


def make_error_analysis():
    return {
        "report_version": "step20_ml_error_analysis_v1",
        "computed_outcomes": 1000,
        "horizon_summary": {
            "20": {
                "up_accuracy": 0.458,
                "downside_underestimation_rate": 0.56,
            }
        },
        "findings": [
            {
                "source": "downside_risk",
                "severity": "critical",
                "target": "max_drop_20d",
            }
        ],
    }


def make_calibration_action():
    return {
        "report_version": "step20_calibration_action_v1",
        "findings": [
            {
                "source": "large_calibration_adjustment",
                "target": "up_20d",
            }
        ],
    }


def make_candidate_model():
    return {
        "report_version": "step20_candidate_model_v2",
        "targets": {
            "up_20d": {
                "promotion_readiness": {"status": "not_ready"},
            }
        },
    }


def test_step20_improvement_summary_keeps_reduced_trust_when_candidate_not_ready():
    report = build_step20_improvement_summary_report(
        error_analysis=make_error_analysis(),
        calibration_action=make_calibration_action(),
        candidate_model_v2=make_candidate_model(),
        generated_at=datetime(2026, 7, 9, tzinfo=UTC),
    )

    assert report["report_version"] == "step20_improvement_summary_v1"
    assert report["final_recommendation"]["status"] == "do_not_promote"
    assert report["decisions"]["ml_reference_policy"] == "reduced_trust"
    assert report["decisions"]["use_downside_risk_overlay"] == "yes"

    markdown = build_step20_improvement_summary_markdown(report)
    assert "# Step 20 ML Improvement Summary" in markdown
    assert "do_not_promote" in markdown


def test_step20_improvement_summary_script_writes_reports(tmp_path, capsys):
    error_path = tmp_path / "error.json"
    calibration_path = tmp_path / "calibration.json"
    candidate_path = tmp_path / "candidate.json"
    error_path.write_text(json.dumps(make_error_analysis()), encoding="utf-8")
    calibration_path.write_text(json.dumps(make_calibration_action()), encoding="utf-8")
    candidate_path.write_text(json.dumps(make_candidate_model()), encoding="utf-8")

    exit_code = script.main(
        [
            "--error-analysis-path",
            str(error_path),
            "--calibration-action-path",
            str(calibration_path),
            "--candidate-model-path",
            str(candidate_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "final_status=do_not_promote" in captured
    assert (tmp_path / "step20_improvement_summary_v1.json").exists()
    assert (tmp_path / "step20_improvement_summary_v1.md").exists()
