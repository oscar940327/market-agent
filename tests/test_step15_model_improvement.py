import json
from datetime import UTC, datetime

import pandas as pd

from ml_model_improvement import (
    TARGET_METRIC_SPECS,
    build_baseline_audit_report,
    build_baseline_audit_summary_markdown,
    build_candidate_model_experiment,
    build_candidate_model_experiment_summary_markdown,
    build_feature_label_diagnostics_report,
    build_feature_label_diagnostics_summary_markdown,
    build_model_comparison_report,
    build_model_comparison_summary_markdown,
    build_target_metric_spec_report,
    build_target_metric_spec_summary_markdown,
)
from scripts import build_step15_model_audit as script
from scripts import build_step15_model_comparison as comparison_script
from scripts import train_step15_candidate_models as candidate_script


def make_baseline_metrics():
    return {
        "model_version": "baseline_v1",
        "targets": {
            "up_5d": make_classification_target(accuracy=0.54, roc_auc=0.55),
            "up_10d": make_classification_target(accuracy=0.52, roc_auc=0.54),
            "up_20d": make_classification_target(accuracy=0.49, roc_auc=0.51),
            "large_drop_20d": make_classification_target(accuracy=0.56, roc_auc=0.57),
        },
    }


def make_classification_target(*, accuracy, roc_auc):
    return {
        "status": "success",
        "row_counts": {"train": 1000, "validation": 300, "test": 250},
        "positive_rates": {"test": 0.52},
        "models": {
            "logistic_regression": {
                "metrics": {
                    "test": {
                        "accuracy": accuracy,
                        "roc_auc": roc_auc,
                        "precision": 0.55,
                        "recall": 0.50,
                    }
                }
            }
        },
    }


def make_return_metrics():
    return {
        "model_version": "return_baseline_v1",
        "targets": {
            "forward_return_5d": make_regression_target(directional_accuracy=0.53),
            "forward_return_10d": make_regression_target(directional_accuracy=0.54),
            "forward_return_20d": make_regression_target(directional_accuracy=0.51),
            "max_drop_20d": make_regression_target(
                directional_accuracy=None,
                downside_underestimation_rate=0.32,
            ),
        },
    }


def make_regression_target(
    *,
    directional_accuracy,
    downside_underestimation_rate=0.18,
):
    metrics = {
        "mae": 0.04,
        "rmse": 0.06,
        "downside_underestimation_rate": downside_underestimation_rate,
    }
    if directional_accuracy is not None:
        metrics["directional_accuracy"] = directional_accuracy
    return {
        "status": "success",
        "row_counts": {"train": 1000, "validation": 300, "test": 250},
        "models": {
            "random_forest_regressor": {
                "metrics": {"test": metrics},
            }
        },
    }


def test_target_metric_spec_contains_core_risk_targets():
    report = build_target_metric_spec_report(
        generated_at=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert report["report_version"] == "step15_target_metric_spec_v1"
    assert "large_drop_20d" in report["targets"]
    assert "max_drop_20d" in report["targets"]
    assert TARGET_METRIC_SPECS["large_drop_20d"]["product_role"].startswith("風險控管")

    markdown = build_target_metric_spec_summary_markdown(report)
    assert "# Step 15 Target / Metric Spec" in markdown
    assert "large_drop_20d" in markdown


def test_baseline_audit_flags_weak_20d_and_downside_risk():
    report = build_baseline_audit_report(
        baseline_metrics=make_baseline_metrics(),
        return_model_metrics=make_return_metrics(),
        monitoring_metrics={"warnings": [{"message": "20d weak"}]},
        calibration_report={"warnings": [{"message": "calibration weak"}]},
        health_report={
            "overall_status": "degraded",
            "ml_reference_policy": {"status": "reduced_trust"},
        },
        generated_at=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert report["report_version"] == "step15_baseline_audit_v1"
    assert report["classification_targets"]["up_20d"]["status"] == "warning"
    assert report["regression_targets"]["max_drop_20d"]["status"] == "warning"
    assert report["finding_summary"]["critical"] >= 2
    assert any("downside" in action for action in report["next_actions"])

    markdown = build_baseline_audit_summary_markdown(report)
    assert "# Step 15 Baseline Audit" in markdown
    assert "up_20d" in markdown


def test_build_step15_model_audit_script_writes_reports(tmp_path, capsys):
    baseline_path = tmp_path / "baseline.json"
    return_path = tmp_path / "return.json"
    monitoring_path = tmp_path / "monitoring.json"
    calibration_path = tmp_path / "calibration.json"
    health_path = tmp_path / "health.json"
    dataset_path = tmp_path / "dataset.csv"
    metadata_path = tmp_path / "metadata.json"
    baseline_path.write_text(json.dumps(make_baseline_metrics()), encoding="utf-8")
    return_path.write_text(json.dumps(make_return_metrics()), encoding="utf-8")
    monitoring_path.write_text(json.dumps({"warnings": []}), encoding="utf-8")
    calibration_path.write_text(json.dumps({"warnings": []}), encoding="utf-8")
    health_path.write_text(
        json.dumps(
            {
                "overall_status": "healthy",
                "ml_reference_policy": {"status": "normal"},
            }
        ),
        encoding="utf-8",
    )
    make_diagnostics_dataset().to_csv(dataset_path, index=False)
    metadata_path.write_text(json.dumps({"row_count": 4}), encoding="utf-8")

    exit_code = script.main(
        [
            "--baseline-metrics-path",
            str(baseline_path),
            "--return-model-metrics-path",
            str(return_path),
            "--monitoring-metrics-path",
            str(monitoring_path),
            "--calibration-path",
            str(calibration_path),
            "--health-path",
            str(health_path),
            "--dataset-path",
            str(dataset_path),
            "--metadata-path",
            str(metadata_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "target_spec_json=" in captured
    assert "audit_json=" in captured
    assert "diagnostics_json=" in captured
    assert (tmp_path / "step15_target_metric_spec_v1.json").exists()
    assert (tmp_path / "step15_baseline_audit_v1.md").exists()
    assert (tmp_path / "step15_feature_label_diagnostics_v1.md").exists()


def test_feature_label_diagnostics_flags_sparse_coverage():
    report = build_feature_label_diagnostics_report(
        make_diagnostics_dataset(),
        metadata={"row_count": 4},
        generated_at=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert report["report_version"] == "step15_feature_label_diagnostics_v1"
    assert report["row_count"] == 4
    assert report["feature_group_summary"]["news"]["news_missing_rate"] == 0.75
    assert report["feature_group_summary"]["similar_cases"]["empty_similar_case_rate"] == 1.0
    assert any(warning["source"] == "similar_cases" for warning in report["warnings"])

    markdown = build_feature_label_diagnostics_summary_markdown(report)
    assert "# Step 15 Feature / Label Diagnostics" in markdown
    assert "similar_cases" in markdown


def test_candidate_model_experiment_uses_core_features_and_reports_best_model():
    dataset = make_candidate_dataset()

    report = build_candidate_model_experiment(
        dataset,
        targets=["up_5d"],
        model_names=["logistic_regression", "random_forest"],
        max_train_rows=40,
        generated_at=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert report["report_version"] == "step15_candidate_model_experiment_v1"
    assert report["feature_policy"]["excluded_feature_groups"] == ["news", "similar_cases"]
    assert report["targets"]["up_5d"]["status"] == "success"
    assert report["targets"]["up_5d"]["best_model"] in {
        "logistic_regression",
        "random_forest",
        "logistic_regression_calibrated_sigmoid",
        "random_forest_calibrated_sigmoid",
    }

    markdown = build_candidate_model_experiment_summary_markdown(report)
    assert "# Step 15 Candidate Model Experiment" in markdown
    assert "up_5d" in markdown


def test_train_step15_candidate_models_script_writes_report(tmp_path, capsys):
    dataset_path = tmp_path / "dataset.csv"
    make_candidate_dataset().to_csv(dataset_path, index=False)

    exit_code = candidate_script.main(
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
    assert exit_code == 0
    assert "target=up_5d status=success" in captured
    assert (tmp_path / "step15_candidate_model_experiment_v1.json").exists()


def test_model_comparison_rejects_not_ready_candidates():
    baseline_audit = build_baseline_audit_report(
        baseline_metrics=make_baseline_metrics(),
        return_model_metrics=make_return_metrics(),
        health_report={
            "overall_status": "degraded",
            "ml_reference_policy": {"status": "reduced_trust"},
        },
    )
    candidate = build_candidate_model_experiment(
        make_candidate_dataset(),
        targets=["up_5d", "up_10d", "up_20d", "large_drop_20d"],
        model_names=["logistic_regression"],
        max_train_rows=40,
    )
    diagnostics = build_feature_label_diagnostics_report(make_diagnostics_dataset())

    report = build_model_comparison_report(
        baseline_audit=baseline_audit,
        candidate_experiment=candidate,
        diagnostics_report=diagnostics,
        generated_at=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert report["report_version"] == "step15_model_comparison_v1"
    assert report["final_recommendation"]["status"] == "do_not_promote"
    assert report["final_recommendation"]["ml_reference_policy"] == "reduced_trust"
    assert report["promotion_policy"]["recommendation"] == "reject"

    markdown = build_model_comparison_summary_markdown(report)
    assert "# Step 15 Model Comparison" in markdown
    assert "do_not_promote" in markdown


def test_build_step15_model_comparison_script_writes_report(tmp_path, capsys):
    baseline_audit = build_baseline_audit_report(
        baseline_metrics=make_baseline_metrics(),
        return_model_metrics=make_return_metrics(),
    )
    candidate = build_candidate_model_experiment(
        make_candidate_dataset(),
        targets=["up_5d"],
        model_names=["logistic_regression"],
        max_train_rows=40,
    )
    diagnostics = build_feature_label_diagnostics_report(make_diagnostics_dataset())
    baseline_path = tmp_path / "baseline_audit.json"
    candidate_path = tmp_path / "candidate.json"
    diagnostics_path = tmp_path / "diagnostics.json"
    baseline_path.write_text(json.dumps(baseline_audit), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    exit_code = comparison_script.main(
        [
            "--baseline-audit-path",
            str(baseline_path),
            "--candidate-experiment-path",
            str(candidate_path),
            "--diagnostics-path",
            str(diagnostics_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "final_status=do_not_promote" in captured
    assert (tmp_path / "step15_model_comparison_v1.json").exists()


def make_diagnostics_dataset():
    return pd.DataFrame(
        [
            make_diagnostics_row("MU", "train", True, False, 1),
            make_diagnostics_row("NVDA", "validation", False, True, 0),
            make_diagnostics_row("AAPL", "test", True, False, 0),
            make_diagnostics_row("AMD", "test", False, False, 0),
        ]
    )


def make_diagnostics_row(ticker, split, up_value, large_drop, news_count):
    return {
        "ticker": ticker,
        "date": "2026-01-02",
        "split": split,
        "price_vs_ma20": 0.01,
        "price_vs_ma50": 0.02,
        "price_vs_ma200": 0.03,
        "rsi_14": 55,
        "macd": 1,
        "macd_histogram": 0.1,
        "volatility_20d": 0.02,
        "volume_ratio_20d": 1.1,
        "market_regime": "bull",
        "qqq_above_ma200": True,
        "qqq_return_20d": 0.02,
        "qqq_return_60d": 0.05,
        "regime_changed": False,
        "news_count_30d": news_count,
        "news_sentiment_score_30d": 0,
        "high_importance_news_count_30d": 0,
        "risk_event_count_30d": 0,
        "earnings_guidance_count_30d": 0,
        "product_demand_count_30d": 0,
        "days_since_last_news": None if news_count == 0 else 3,
        "news_missing": news_count == 0,
        "similar_case_sample_size": 0,
        "similar_case_win_rate_5d": None,
        "similar_case_win_rate_10d": None,
        "similar_case_win_rate_20d": None,
        "similar_case_average_return_20d": None,
        "similar_case_max_loss_20d": None,
        "similar_case_evidence_quality": "none",
        "up_5d": up_value,
        "up_10d": up_value,
        "up_20d": up_value,
        "large_drop_20d": large_drop,
        "forward_return_5d": 0.01,
        "forward_return_10d": 0.02,
        "forward_return_20d": 0.03,
        "max_drop_20d": -0.04,
    }


def make_candidate_dataset():
    rows = []
    for index in range(90):
        if index < 50:
            split = "train"
        elif index < 70:
            split = "validation"
        else:
            split = "test"
        positive = index % 4 in {0, 1}
        rows.append(
            {
                **make_diagnostics_row(
                    ticker=f"T{index % 5}",
                    split=split,
                    up_value=positive,
                    large_drop=not positive and index % 3 == 0,
                    news_count=0,
                ),
                "date": f"2024-01-{(index % 28) + 1:02d}",
                "price_vs_ma5": 0.05 if positive else -0.03,
                "price_vs_ma10": 0.04 if positive else -0.02,
                "price_vs_ma20": 0.03 if positive else -0.01,
                "macd_histogram": 0.2 if positive else -0.2,
                "rsi_14": 62 if positive else 42,
                "forward_return_5d": 0.02 if positive else -0.01,
                "forward_return_10d": 0.03 if positive else -0.02,
                "forward_return_20d": 0.05 if positive else -0.04,
                "max_drop_20d": -0.02 if positive else -0.10,
            }
        )
    return pd.DataFrame(rows)
