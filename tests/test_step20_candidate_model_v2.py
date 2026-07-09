import json

from scripts import build_step20_candidate_model_v2 as script
from tests.test_step15_model_improvement import make_candidate_dataset


def test_step20_candidate_model_v2_script_writes_step20_report(tmp_path, capsys):
    dataset_path = tmp_path / "dataset.csv"
    make_candidate_dataset().to_csv(dataset_path, index=False)

    exit_code = script.main(
        [
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(tmp_path),
            "--targets",
            "up_5d",
            "--models",
            "logistic_regression",
            "--max-train-rows",
            "40",
        ]
    )

    captured = capsys.readouterr().out
    json_path = tmp_path / "step20_candidate_model_v2.json"
    markdown_path = tmp_path / "step20_candidate_model_v2.md"

    assert exit_code == 0
    assert "target=up_5d status=success" in captured
    assert json_path.exists()
    assert markdown_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["report_version"] == "step20_candidate_model_v2"
    assert report["step20_context"]["uses_existing_step15_trainer"] is True
    assert "# Step 20 Candidate Model v2 Experiment" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_step20_candidate_report_conversion_keeps_recommendations():
    report = script.convert_to_step20_report(
        {
            "report_version": "step15_candidate_model_experiment_v1",
            "recommendations": ["Keep baseline."],
            "targets": {},
        }
    )

    assert report["report_version"] == "step20_candidate_model_v2"
    assert "Keep baseline." in report["recommendations"]
    assert any("Step 20 candidate v2" in item for item in report["recommendations"])
