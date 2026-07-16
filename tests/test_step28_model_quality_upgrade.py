import json
from datetime import UTC, datetime

import pandas as pd

from ml_model_improvement import (
    QUALITY_POLICY,
    build_step28_quality_upgrade,
    build_step28_summary_markdown,
    build_walk_forward_folds,
)
from scripts import build_step28_model_quality_upgrade as script
from ml_model_improvement.quality_upgrade import choose_recall_threshold
from agent.ml_model_policy import build_step28_policy


def test_walk_forward_folds_keep_training_before_evaluation():
    dataset = make_dataset()
    prepared = dataset.assign(_date=pd.to_datetime(dataset["date"]))

    folds = build_walk_forward_folds(prepared)

    assert len(folds) == 3
    for fold in folds:
        train_dates = prepared.loc[fold["train_index"], "_date"]
        test_dates = prepared.loc[fold["test_index"], "_date"]
        assert train_dates.max() < test_dates.min()
    assert folds[-1]["role"] == "holdout"


def test_step28_report_evaluates_all_targets_without_auto_promotion():
    report = build_step28_quality_upgrade(
        make_dataset(),
        classification_models=["logistic_regression"],
        regression_models=["hist_gradient_boosting"],
        max_train_rows=500,
        max_evaluation_rows=500,
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert report["report_version"] == "step28_model_quality_upgrade_v1"
    assert report["evaluation_design"]["method"] == "expanding_walk_forward_with_final_holdout"
    assert len(report["targets"]) == 8
    assert report["targets"]["up_5d"]["best_candidate"] in {
        "logistic_regression",
        "logistic_regression_calibrated_sigmoid",
    }
    assert report["targets"]["forward_return_20d"]["best_candidate"] == "hist_gradient_boosting"
    assert report["promotion"]["automatic_replacement"] is False
    assert report["targets"]["up_5d"]["quality"]["level"] in {
        "high",
        "medium",
        "low_to_medium",
        "low",
    }
    assert QUALITY_POLICY["classification"]["minimum_roc_auc"] == 0.53

    markdown = build_step28_summary_markdown(report)
    assert "# Step 28 ML Model Quality Upgrade" in markdown
    assert "up_20d" in markdown
    assert "Candidate models never replace production automatically" in markdown


def test_step28_script_writes_json_and_markdown(tmp_path, capsys):
    dataset_path = tmp_path / "dataset.csv"
    make_dataset().to_csv(dataset_path, index=False)

    exit_code = script.main(
        [
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(tmp_path),
            "--classification-models",
            "logistic_regression",
            "--regression-models",
            "hist_gradient_boosting",
            "--max-train-rows",
            "500",
            "--max-evaluation-rows",
            "500",
        ]
    )

    output = capsys.readouterr().out
    json_path = tmp_path / "step28_model_quality_upgrade_v1.json"
    markdown_path = tmp_path / "step28_model_quality_upgrade_v1.md"
    assert exit_code == 0
    assert "promotion_status=" in output
    assert json_path.exists()
    assert markdown_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["quality_policy"]["promotion"]["automatic_replacement"] is False


def test_large_drop_threshold_prioritizes_recall():
    labels = pd.Series([True, True, False, False, False])
    probabilities = pd.Series([0.42, 0.31, 0.29, 0.10, 0.05])

    threshold = choose_recall_threshold(labels, probabilities, minimum_recall=0.80)

    assert threshold == 0.30


def test_step28_policy_keeps_bundle_reduced_trust_and_exposes_target_results():
    policy = build_step28_policy(
        {
            "report_version": "step28_model_quality_upgrade_v1",
            "ml_reference_policy": "reduced_trust",
            "promotion": {
                "status": "do_not_promote",
                "passed_targets": ["large_drop_20d"],
                "blocked_targets": ["up_20d", "max_drop_20d"],
                "action": "keep current production models",
            },
            "targets": {
                "large_drop_20d": {
                    "best_candidate": "random_forest_calibrated_sigmoid",
                    "promotion_decision": "pass",
                    "quality": {"level": "medium", "failed_checks": []},
                },
                "up_20d": {
                    "best_candidate": "random_forest",
                    "promotion_decision": "reject",
                    "quality": {
                        "level": "low",
                        "failed_checks": ["holdout_roc_auc"],
                    },
                },
            },
        }
    )

    assert policy["status"] == "reduced_trust"
    assert policy["candidate_promoted"] is False
    assert policy["passed_targets"] == ["large_drop_20d"]
    assert policy["target_quality"]["up_20d"]["quality"] == "low"
    assert policy["downside_overlay_enabled"] is True


def make_dataset() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2018-01-05", "2026-06-26", freq="2W-FRI")
    for date_index, row_date in enumerate(dates):
        for ticker_index, ticker in enumerate(["MU", "NVDA", "AAPL", "AMD"]):
            signal = 1 if (date_index + ticker_index) % 4 in {0, 1} else -1
            regime = ["bull", "bear", "sideways"][(date_index // 20) % 3]
            noise = ((date_index + ticker_index) % 5 - 2) * 0.002
            return_5d = signal * 0.02 + noise
            return_10d = signal * 0.03 + noise
            return_20d = signal * 0.05 + noise
            max_drop = -0.03 if signal > 0 else -0.10
            rows.append(
                {
                    "ticker": ticker,
                    "date": row_date.date().isoformat(),
                    "market_regime": regime,
                    "volatility_regime": "high" if signal < 0 else "normal",
                    "price_vs_ma5": signal * 0.04,
                    "price_vs_ma10": signal * 0.035,
                    "price_vs_ma20": signal * 0.03,
                    "price_vs_ma50": signal * 0.02,
                    "price_vs_ma200": signal * 0.01,
                    "ma5_vs_ma20": signal * 0.02,
                    "ma20_vs_ma50": signal * 0.01,
                    "ma50_vs_ma200": signal * 0.005,
                    "rsi_14": 62 if signal > 0 else 38,
                    "macd": signal * 0.5,
                    "macd_histogram": signal * 0.2,
                    "return_5d": signal * 0.01,
                    "return_10d": signal * 0.015,
                    "return_20d": signal * 0.025,
                    "volatility_20d": 0.02 if signal > 0 else 0.05,
                    "volume_ratio_20d": 1.2 if signal > 0 else 0.8,
                    "qqq_return_20d": signal * 0.01,
                    "qqq_return_60d": signal * 0.02,
                    "up_5d": return_5d > 0,
                    "up_10d": return_10d > 0,
                    "up_20d": return_20d > 0,
                    "large_drop_20d": max_drop <= -0.08,
                    "forward_return_5d": return_5d,
                    "forward_return_10d": return_10d,
                    "forward_return_20d": return_20d,
                    "max_drop_20d": max_drop,
                }
            )
    return pd.DataFrame(rows)
