import json

from ml_return_model import (
    EXPERIMENT_VERSION,
    run_boosting_return_experiment,
    write_boosting_experiment_outputs,
)
from tests.test_step7_return_model import make_return_model_dataset


def test_boosting_experiment_reports_optional_model_availability(tmp_path):
    result = run_boosting_return_experiment(make_return_model_dataset())
    output_paths = write_boosting_experiment_outputs(
        result=result,
        report_dir=tmp_path / "reports",
    )

    assert result["experiment_version"] == EXPERIMENT_VERSION
    assert result["usage_policy"] == "comparison_only"
    assert set(result["targets"]) == {
        "forward_return_5d",
        "forward_return_10d",
        "forward_return_20d",
        "max_drop_20d",
    }
    assert "available_models" in result
    assert "skipped_models" in result
    assert output_paths["metrics_path"].endswith(
        "return_boosting_experiment_metrics_v1.json"
    )
    assert output_paths["summary_path"].endswith(
        "return_boosting_experiment_summary_v1.md"
    )

    metrics = json.loads(
        (tmp_path / "reports" / "return_boosting_experiment_metrics_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert metrics["experiment_version"] == EXPERIMENT_VERSION


def test_boosting_experiment_skips_targets_when_optional_models_are_missing():
    result = run_boosting_return_experiment(make_return_model_dataset())

    if result["available_models"]:
        assert any(
            target_result["status"] == "success"
            for target_result in result["targets"].values()
        )
    else:
        assert result["skipped_models"]["xgboost"] == "package_not_installed"
        assert result["skipped_models"]["lightgbm"] == "package_not_installed"
        assert all(
            target_result["reason"] == "no_optional_models_available"
            for target_result in result["targets"].values()
        )
