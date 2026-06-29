import json

import pandas as pd

from ml_baseline import BASELINE_TARGETS, train_baseline_models, write_baseline_outputs
from ml_dataset import FEATURE_COLUMNS


def make_baseline_dataset():
    rows = []
    splits = (
        ["train"] * 80
        + ["validation"] * 30
        + ["test"] * 30
    )
    for index, split in enumerate(splits):
        bullish = index % 4 in {0, 1}
        price_vs_ma20 = 0.05 if bullish else -0.04
        macd_histogram = 0.5 if bullish else -0.5
        rsi_14 = 60 if bullish else 40
        row = {
            "ticker": "MU" if index % 2 == 0 else "NVDA",
            "date": f"2022-01-{(index % 28) + 1:02d}",
            "split": split,
            "feature_version": "ml_features_v1",
            "label_version": "ml_labels_v1",
            "data_as_of": f"2022-01-{(index % 28) + 1:02d}",
            "price_vs_ma5": price_vs_ma20,
            "price_vs_ma10": price_vs_ma20,
            "price_vs_ma20": price_vs_ma20,
            "price_vs_ma50": price_vs_ma20,
            "price_vs_ma200": price_vs_ma20,
            "ma5_vs_ma20": price_vs_ma20 / 2,
            "ma20_vs_ma50": price_vs_ma20 / 2,
            "ma50_vs_ma200": price_vs_ma20 / 2,
            "rsi_14": rsi_14,
            "macd": macd_histogram,
            "macd_histogram": macd_histogram,
            "is_breakout": bullish,
            "is_volume_surge": index % 5 == 0,
            "is_pullback": not bullish and index % 3 == 0,
            "return_5d": 0.02 if bullish else -0.01,
            "return_10d": 0.03 if bullish else -0.02,
            "return_20d": 0.04 if bullish else -0.03,
            "volatility_20d": 0.02 if bullish else 0.06,
            "volume_ratio_20d": 1.2 if bullish else 0.8,
            "market_regime": "bull" if bullish else "bear",
            "qqq_above_ma200": bullish,
            "qqq_return_20d": 0.03 if bullish else -0.03,
            "qqq_return_60d": 0.08 if bullish else -0.08,
            "regime_changed": False,
            "news_count_30d": 1,
            "news_sentiment_score_30d": 0.5 if bullish else -0.5,
            "high_importance_news_count_30d": 1 if bullish else 0,
            "risk_event_count_30d": 0 if bullish else 1,
            "earnings_guidance_count_30d": 1 if bullish else 0,
            "product_demand_count_30d": 1 if bullish else 0,
            "days_since_last_news": 3,
            "news_missing": False,
            "similar_case_sample_size": 30,
            "similar_case_win_rate_5d": 0.6 if bullish else 0.4,
            "similar_case_win_rate_10d": 0.6 if bullish else 0.4,
            "similar_case_win_rate_20d": 0.65 if bullish else 0.35,
            "similar_case_average_return_20d": 0.04 if bullish else -0.03,
            "similar_case_max_loss_20d": -0.04 if bullish else -0.12,
            "similar_case_evidence_quality": "medium",
            "up_5d": bullish,
            "up_10d": bullish,
            "up_20d": bullish,
            "large_drop_20d": not bullish,
        }
        for feature in FEATURE_COLUMNS:
            row.setdefault(feature, 0)
        rows.append(row)
    return pd.DataFrame(rows)


def test_train_baseline_models_outputs_metrics_for_all_targets():
    result = train_baseline_models(make_baseline_dataset())

    assert set(result["targets"]) == set(BASELINE_TARGETS)
    for target in BASELINE_TARGETS:
        target_result = result["targets"][target]
        assert target_result["status"] == "success"
        assert "rule_based" in target_result["models"]
        assert "logistic_regression" in target_result["models"]
        assert "random_forest" in target_result["models"]
        assert (
            target_result["models"]["logistic_regression"]["metrics"]["validation"][
                "accuracy"
            ]
            >= 0.9
        )
        assert target_result["models"]["random_forest"]["feature_importance"]


def test_write_baseline_outputs_creates_reports_and_model_files(tmp_path):
    result = train_baseline_models(make_baseline_dataset())
    output = write_baseline_outputs(
        result=result,
        report_dir=tmp_path / "reports",
        model_dir=tmp_path / "models",
    )

    metrics = json.loads(
        (tmp_path / "reports" / "baseline_metrics_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert metrics["model_version"] == "baseline_v1"
    assert "up_20d" in metrics["targets"]
    assert (tmp_path / "reports" / "baseline_feature_importance_v1.json").exists()
    assert (tmp_path / "reports" / "baseline_summary_v1.md").exists()
    assert len(output["model_paths"]) == 8
