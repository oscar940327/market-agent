import json

from agent.analyst import format_single_stock_analysis
from ml_baseline import train_baseline_models, write_baseline_outputs
from ml_research import build_ml_research_output
from tests.test_step6_news_events import make_single_stock_report_data
from tests.test_step7_ml_baseline import make_baseline_dataset


def test_build_ml_research_output_contains_reference_schema(tmp_path):
    dataset = make_baseline_dataset()
    training_result = train_baseline_models(dataset)
    write_baseline_outputs(
        result=training_result,
        report_dir=tmp_path / "reports",
        model_dir=tmp_path / "models",
    )
    metadata_path = tmp_path / "training_dataset_v1_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "data_end_date": "2026-06-29",
                "row_count": len(dataset),
            }
        ),
        encoding="utf-8",
    )

    output = build_ml_research_output(
        feature_row=dataset.iloc[-1].to_dict(),
        model_dir=tmp_path / "models",
        metrics_path=tmp_path / "reports" / "baseline_metrics_v1.json",
        dataset_metadata_path=metadata_path,
        return_reference={
            "method": "historical_quantile_reference",
            "historical_average_return_5d": 0.01,
            "expected_return_range_5d": {
                "low": -0.02,
                "high": 0.03,
            },
            "upside_return_range_5d": {
                "low": 0.01,
                "high": 0.04,
            },
            "max_drop_range_20d": {
                "low": -0.12,
                "high": -0.04,
            },
        },
    )

    assert output["status"] == "success"
    assert output["usage_policy"] == "reference_only"
    assert output["model_version"] == "baseline_v1"
    assert output["training_data_as_of"] == "2026-06-29"
    assert output["dataset_rows"] == len(dataset)
    assert set(output["targets"]) == {
        "up_5d",
        "up_10d",
        "up_20d",
        "large_drop_20d",
    }
    for target_output in output["targets"].values():
        assert 0 <= target_output["probability"] <= 1
        assert 0 <= target_output["probability_percent"] <= 100
        assert target_output["signal_label"]
        assert target_output["signal_quality"] in {
            "high",
            "medium",
            "low_to_medium",
            "low",
            "unknown",
        }

    assert "large-drop risk" in output["risk_note"]
    assert "5-day upside probability" in output["summary"]
    assert output["return_reference"]["method"] == "historical_quantile_reference"
    assert output["return_reference"]["historical_average_return_5d"] == 0.01
    assert output["return_reference"]["expected_return_range_5d"]["low"] == -0.02
    assert output["return_reference"]["upside_return_range_5d"]["high"] == 0.04
    assert output["return_reference"]["max_drop_range_20d"]["low"] == -0.12


def test_ml_research_output_can_use_pending_return_reference(tmp_path):
    dataset = make_baseline_dataset()
    training_result = train_baseline_models(dataset)
    write_baseline_outputs(
        result=training_result,
        report_dir=tmp_path / "reports",
        model_dir=tmp_path / "models",
    )

    output = build_ml_research_output(
        feature_row=dataset.iloc[0].to_dict(),
        model_dir=tmp_path / "models",
        metrics_path=tmp_path / "reports" / "baseline_metrics_v1.json",
    )

    assert output["return_reference"]["method"] == "historical_reference_pending"
    assert output["return_reference"]["expected_return_range_20d"] is None


def test_single_stock_report_displays_successful_ml_reference():
    data = make_single_stock_report_data(
        news_events_summary={
            "status": "no_recent_news",
            "lookback_days": 30,
        }
    )
    data["ml_research"] = {
        "status": "success",
        "usage_policy": "reference_only",
        "targets": {
            "up_5d": {
                "probability_percent": 43.3,
                "signal_label": "slightly bearish",
                "signal_quality": "low",
            },
            "up_10d": {
                "probability_percent": 41.6,
                "signal_label": "slightly bearish",
                "signal_quality": "low",
            },
            "up_20d": {
                "probability_percent": 49.4,
                "signal_label": "unclear direction",
                "signal_quality": "low",
            },
            "large_drop_20d": {
                "probability_percent": 78.8,
                "signal_label": "high large-drop risk",
                "signal_quality": "medium",
            },
        },
        "risk_note": (
            "ML baseline estimates 20-day large-drop risk at 78.8% "
            "(high large-drop risk). Use this as a risk-control reference only."
        ),
        "return_reference": {
            "method": "historical_quantile_reference",
            "sample_size": 120,
            "evidence_quality": "medium",
            "expected_return_range_5d": {"low": -0.01, "high": 0.03},
            "upside_return_range_5d": {"low": 0.01, "high": 0.04},
            "historical_average_return_5d": 0.012,
            "max_drop_range_20d": {"low": -0.12, "high": -0.04},
            "note": "Return ranges are historical references, not guaranteed outcomes.",
        },
    }

    report = format_single_stock_analysis(data)

    assert "ML Reference" in report
    assert "信任狀態：降低信任" in report
    assert "5-day upside probability: 43.3% (slightly bearish)" in report
    assert "20-day large-drop risk: 78.8% (high large-drop risk)" in report
    assert "20 日預測提醒" in report
    assert "大跌風險提醒" in report
    assert "Model quality: upside direction signals are low" in report
    assert "ML baseline estimates 20-day large-drop risk at 78.8%" in report
    assert "5d expected return range: -1.0% ~ 3.0%" in report
    assert "5d upside scenario range: 1.0% ~ 4.0%" in report
    assert "20d max-drop range: -12.0% ~ -4.0%" in report


def test_single_stock_report_displays_unavailable_ml_reference():
    data = make_single_stock_report_data(news_events_summary=None)
    data["ml_research"] = {
        "status": "unavailable",
        "usage_policy": "reference_only",
        "reason": "missing_ml_artifacts",
        "message": "Training dataset not found.",
    }

    report = format_single_stock_analysis(data)

    assert "ML Reference" in report
    assert "信任狀態：暫時不可用" in report
    assert "ML reference is currently unavailable" in report
    assert "missing_ml_artifacts" in report


def test_single_stock_report_displays_data_freshness_warnings():
    data = make_single_stock_report_data(news_events_summary=None)
    data["data_freshness"] = {
        "overall": "warning",
        "warnings": [
            {
                "source": "ml_training_data",
                "status": "warning",
                "reason": "ml_training_data_getting_old",
                "message": "ML training dataset 已超過 7 天未更新。",
            }
        ],
    }

    report = format_single_stock_analysis(data)

    assert "資料新鮮度提醒" in report
    assert "ML training dataset 已超過 7 天未更新" in report
