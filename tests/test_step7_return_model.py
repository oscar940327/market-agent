import json

import pandas as pd

from agent.analyst import format_single_stock_analysis
from ml_return_model import (
    RETURN_MODEL_TARGETS,
    build_return_model_output,
    train_return_models,
    write_return_model_outputs,
)
from ml_dataset import FEATURE_COLUMNS
from tests.test_step6_news_events import make_single_stock_report_data


def make_return_model_dataset():
    rows = []
    splits = ["train"] * 90 + ["validation"] * 30 + ["test"] * 30
    for index, split in enumerate(splits):
        strength = (index % 20) / 20
        forward_5d = -0.03 + strength * 0.08
        forward_10d = -0.04 + strength * 0.10
        forward_20d = -0.06 + strength * 0.14
        max_drop = -0.14 + strength * 0.10
        row = {
            "ticker": "MU" if index % 2 == 0 else "NVDA",
            "date": f"2022-01-{(index % 28) + 1:02d}",
            "split": split,
            "feature_version": "ml_features_v1",
            "label_version": "ml_labels_v1",
            "price_vs_ma5": strength - 0.5,
            "price_vs_ma10": strength - 0.5,
            "price_vs_ma20": strength - 0.5,
            "price_vs_ma50": strength - 0.5,
            "price_vs_ma200": strength - 0.5,
            "ma5_vs_ma20": strength - 0.5,
            "ma20_vs_ma50": strength - 0.5,
            "ma50_vs_ma200": strength - 0.5,
            "rsi_14": 40 + strength * 30,
            "macd": strength,
            "macd_histogram": strength - 0.5,
            "is_breakout": strength > 0.65,
            "is_volume_surge": index % 5 == 0,
            "is_pullback": strength < 0.25,
            "return_5d": forward_5d,
            "return_10d": forward_10d,
            "return_20d": forward_20d,
            "volatility_20d": 0.02 + (1 - strength) * 0.04,
            "volume_ratio_20d": 0.8 + strength,
            "market_regime": "bull" if strength > 0.4 else "bear",
            "qqq_above_ma200": strength > 0.4,
            "qqq_return_20d": forward_20d,
            "qqq_return_60d": forward_20d * 2,
            "regime_changed": False,
            "news_count_30d": 1,
            "news_sentiment_score_30d": strength - 0.5,
            "high_importance_news_count_30d": 1 if strength > 0.5 else 0,
            "risk_event_count_30d": 1 if strength < 0.25 else 0,
            "earnings_guidance_count_30d": 1 if strength > 0.5 else 0,
            "product_demand_count_30d": 1 if strength > 0.5 else 0,
            "days_since_last_news": 2,
            "news_missing": False,
            "similar_case_sample_size": 40,
            "similar_case_win_rate_5d": strength,
            "similar_case_win_rate_10d": strength,
            "similar_case_win_rate_20d": strength,
            "similar_case_average_return_20d": forward_20d,
            "similar_case_max_loss_20d": max_drop,
            "similar_case_evidence_quality": "medium",
            "forward_return_5d": forward_5d,
            "forward_return_10d": forward_10d,
            "forward_return_20d": forward_20d,
            "max_drop_20d": max_drop,
        }
        for feature in FEATURE_COLUMNS:
            row.setdefault(feature, 0)
        rows.append(row)
    return pd.DataFrame(rows)


def test_train_return_models_outputs_metrics_for_targets():
    result = train_return_models(make_return_model_dataset())

    assert set(result["targets"]) == set(RETURN_MODEL_TARGETS)
    for target in RETURN_MODEL_TARGETS:
        target_result = result["targets"][target]
        assert target_result["status"] == "success"
        assert "random_forest_regressor" in target_result["models"]
        assert "quantile_regressor" in target_result["models"]
        assert (
            target_result["models"]["random_forest_regressor"]["metrics"]["validation"][
                "mae"
            ]
            < 0.05
        )
        assert "coverage" in target_result["models"]["quantile_regressor"]["metrics"][
            "validation"
        ]


def test_return_model_outputs_and_inference(tmp_path):
    dataset = make_return_model_dataset()
    result = train_return_models(dataset)
    output_paths = write_return_model_outputs(
        result=result,
        report_dir=tmp_path / "reports",
        model_dir=tmp_path / "models",
    )

    metrics = json.loads(
        (tmp_path / "reports" / "return_model_metrics_v1.json").read_text(
            encoding="utf-8"
        )
    )
    inference = build_return_model_output(
        feature_row=dataset.iloc[-1].to_dict(),
        model_dir=tmp_path / "models",
        metrics_path=tmp_path / "reports" / "return_model_metrics_v1.json",
    )

    assert metrics["model_version"] == "return_baseline_v1"
    assert len(output_paths["model_paths"]) == 12
    assert inference["status"] == "success"
    assert inference["usage_policy"] == "experimental_reference_only"
    assert set(inference["targets"]) == set(RETURN_MODEL_TARGETS)
    assert "predicted_range" in inference["targets"]["forward_return_20d"]


def test_single_stock_report_displays_return_model_numbers():
    data = make_single_stock_report_data(news_events_summary=None)
    data["ml_research"] = {
        "status": "success",
        "targets": {
            "up_5d": {
                "probability_percent": 51.0,
                "signal_label": "unclear direction",
                "signal_quality": "low",
            },
            "up_10d": {
                "probability_percent": 52.0,
                "signal_label": "unclear direction",
                "signal_quality": "low",
            },
            "up_20d": {
                "probability_percent": 53.0,
                "signal_label": "slightly bullish",
                "signal_quality": "low",
            },
            "large_drop_20d": {
                "probability_percent": 25.0,
                "signal_label": "low-to-medium large-drop risk",
                "signal_quality": "medium",
            },
        },
        "return_model": {
            "status": "success",
            "targets": {
                "forward_return_5d": {
                    "predicted_percent": 0.8,
                    "predicted_range": {"low_percent": -1.0, "high_percent": 2.5},
                    "model_quality": "low_to_medium",
                },
                "forward_return_10d": {
                    "predicted_percent": 1.4,
                    "predicted_range": {"low_percent": -2.0, "high_percent": 4.0},
                    "model_quality": "low_to_medium",
                },
                "forward_return_20d": {
                    "predicted_percent": 2.4,
                    "predicted_range": {"low_percent": -4.0, "high_percent": 8.5},
                    "model_quality": "low_to_medium",
                },
                "max_drop_20d": {
                    "predicted_percent": -7.2,
                    "predicted_range": {"low_percent": -11.0, "high_percent": -3.5},
                    "model_quality": "low_to_medium",
                },
            },
            "summary": "Return model is experimental.",
        },
    }

    report = format_single_stock_analysis(data)

    assert "Return model: experimental reference only" in report
    assert "Predicted 5d return: 0.8% (range -1.0% ~ 2.5%" in report
    assert "Predicted 20d max drop: -7.2% (range -11.0% ~ -3.5%" in report
