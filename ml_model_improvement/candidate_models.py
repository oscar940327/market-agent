from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml_baseline.trainer import (
    CATEGORICAL_FEATURES,
    build_raw_feature_frame,
    normalize_target,
)
from ml_model_improvement.target_spec import TARGET_METRIC_SPECS


CANDIDATE_TARGETS = ["up_5d", "up_10d", "up_20d", "large_drop_20d"]
CORE_FEATURES = [
    "price_vs_ma5",
    "price_vs_ma10",
    "price_vs_ma20",
    "price_vs_ma50",
    "price_vs_ma200",
    "ma5_vs_ma20",
    "ma20_vs_ma50",
    "ma50_vs_ma200",
    "rsi_14",
    "macd",
    "macd_histogram",
    "is_breakout",
    "is_volume_surge",
    "is_pullback",
    "return_5d",
    "return_10d",
    "return_20d",
    "volatility_20d",
    "volume_ratio_20d",
    "market_regime",
    "qqq_above_ma200",
    "qqq_return_20d",
    "qqq_return_60d",
    "regime_changed",
]
DEFAULT_MODEL_NAMES = [
    "logistic_regression",
    "random_forest",
    "xgboost",
    "lightgbm",
]


def build_candidate_model_experiment(
    dataset: pd.DataFrame,
    *,
    targets: list[str] | None = None,
    model_names: list[str] | None = None,
    max_train_rows: int = 120_000,
    random_state: int = 42,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    targets = targets or CANDIDATE_TARGETS
    model_names = model_names or DEFAULT_MODEL_NAMES
    results = {
        "report_version": "step15_candidate_model_experiment_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "feature_policy": {
            "name": "technical_market_core_v1",
            "included_feature_groups": ["technical", "market"],
            "excluded_feature_groups": ["news", "similar_cases"],
            "reason": "Step 15 diagnostics found news and similar-case coverage too sparse for core candidate training.",
        },
        "targets": {},
        "recommendations": [],
    }
    for target in targets:
        results["targets"][target] = run_target_experiment(
            dataset,
            target=target,
            model_names=model_names,
            max_train_rows=max_train_rows,
            random_state=random_state,
        )
    results["recommendations"] = build_candidate_recommendations(results)
    return results


def run_target_experiment(
    dataset: pd.DataFrame,
    *,
    target: str,
    model_names: list[str],
    max_train_rows: int,
    random_state: int,
) -> dict:
    if target not in dataset.columns:
        return {"status": "skipped", "reason": "missing_target_column"}
    target_frame = dataset.dropna(subset=[target]).copy()
    split_frames = {
        split: target_frame[target_frame["split"] == split].copy()
        for split in ["train", "validation", "test"]
    }
    if split_frames["train"].empty or split_frames["validation"].empty:
        return {"status": "skipped", "reason": "missing_train_or_validation_split"}
    if split_frames["train"][target].map(to_bool).nunique() < 2:
        return {"status": "skipped", "reason": "train_split_has_single_class"}

    train_frame = sample_train_frame(
        split_frames["train"],
        max_train_rows=max_train_rows,
        random_state=random_state,
    )
    fit_frames = {**split_frames, "train": train_frame}
    matrices = build_candidate_feature_matrices(fit_frames)
    models = build_candidate_models(
        model_names=model_names,
        train_target=train_frame[target],
        random_state=random_state,
    )
    result = {
        "status": "success",
        "row_counts": {
            split: int(len(frame)) for split, frame in split_frames.items()
        },
        "training_row_count_used": int(len(train_frame)),
        "models": {},
    }
    for model_name, model in models.items():
        if model is None:
            result["models"][model_name] = {
                "status": "skipped",
                "reason": "dependency_unavailable",
            }
            continue
        y_train = normalize_target(train_frame[target])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(matrices["train"], y_train)
        result["models"][model_name] = {
            "status": "success",
            "metrics": evaluate_model_by_split(
                model=model,
                split_frames=fit_frames,
                matrices=matrices,
                target=target,
            ),
        }
        calibrated = build_calibrated_model(
            model=model,
            validation_matrix=matrices["validation"],
            validation_target=split_frames["validation"][target],
        )
        if calibrated is not None:
            calibrated_name = f"{model_name}_calibrated_sigmoid"
            result["models"][calibrated_name] = {
                "status": "success",
                "calibration_method": "sigmoid",
                "metrics": evaluate_model_by_split(
                    model=calibrated,
                    split_frames=fit_frames,
                    matrices=matrices,
                    target=target,
                ),
            }
    result["best_model"] = choose_best_candidate(result["models"])
    result["promotion_readiness"] = classify_promotion_readiness(
        target=target,
        model_result=result["models"].get(result["best_model"]) if result["best_model"] else None,
    )
    return result


def build_candidate_feature_matrices(split_frames: dict[str, pd.DataFrame]) -> dict:
    train_features = select_core_features(build_raw_feature_frame(split_frames["train"]))
    numeric_medians = {
        column: train_features[column].median()
        for column in train_features.columns
    }
    matrices = {}
    for split, frame in split_frames.items():
        features = select_core_features(build_raw_feature_frame(frame))
        for column in train_features.columns:
            if column not in features:
                features[column] = 0
        features = features[train_features.columns]
        for column, median in numeric_medians.items():
            features[column] = features[column].fillna(0 if pd.isna(median) else median)
        matrices[split] = features
    return matrices


def select_core_features(features: pd.DataFrame) -> pd.DataFrame:
    selected_columns = [
        column
        for column in features.columns
        if is_core_feature_column(column)
    ]
    return features[selected_columns].copy()


def is_core_feature_column(column: str) -> bool:
    if column in CORE_FEATURES:
        return True
    for feature in CATEGORICAL_FEATURES:
        if feature in CORE_FEATURES and column.startswith(f"{feature}__"):
            return True
    return False


def build_candidate_models(
    *,
    model_names: list[str],
    train_target: pd.Series,
    random_state: int,
) -> dict:
    models = {}
    for model_name in model_names:
        if model_name == "logistic_regression":
            models[model_name] = LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                solver="liblinear",
                random_state=random_state,
            )
        elif model_name == "random_forest":
            models[model_name] = RandomForestClassifier(
                n_estimators=120,
                max_depth=10,
                min_samples_leaf=40,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=random_state,
            )
        elif model_name == "xgboost":
            models[model_name] = build_xgboost_classifier(
                train_target=train_target,
                random_state=random_state,
            )
        elif model_name == "lightgbm":
            models[model_name] = build_lightgbm_classifier(random_state=random_state)
    return models


def build_calibrated_model(
    *,
    model,
    validation_matrix: pd.DataFrame,
    validation_target: pd.Series,
):
    y_validation = normalize_target(validation_target)
    if y_validation.nunique() < 2:
        return None
    calibrated = CalibratedClassifierCV(
        estimator=FrozenEstimator(model),
        method="sigmoid",
        cv=None,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        calibrated.fit(validation_matrix, y_validation)
    return calibrated


def build_xgboost_classifier(*, train_target: pd.Series, random_state: int):
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return None
    y_train = normalize_target(train_target)
    positives = int(y_train.sum())
    negatives = int(len(y_train) - positives)
    scale_pos_weight = negatives / positives if positives else 1.0
    return XGBClassifier(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        n_jobs=-1,
        random_state=random_state,
    )


def build_lightgbm_classifier(*, random_state: int):
    try:
        from lightgbm import LGBMClassifier
    except ImportError:
        return None
    return LGBMClassifier(
        n_estimators=180,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.85,
        colsample_bytree=0.85,
        class_weight="balanced",
        n_jobs=-1,
        random_state=random_state,
        verbose=-1,
    )


def evaluate_model_by_split(
    *,
    model,
    split_frames: dict[str, pd.DataFrame],
    matrices: dict[str, pd.DataFrame],
    target: str,
) -> dict:
    metrics = {}
    for split, frame in split_frames.items():
        if frame.empty:
            continue
        y_true = normalize_target(frame[target])
        y_pred = normalize_target(model.predict(matrices[split]))
        y_score = predict_probability(model, matrices[split])
        metrics[split] = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "roc_auc": safe_roc_auc(y_true, y_score),
            "brier_score": safe_brier_score(y_true, y_score),
            "positive_rate": float(y_true.mean()),
            "predicted_positive_rate": float(y_pred.mean()),
            "rows": int(len(y_true)),
        }
    return metrics


def choose_best_candidate(models: dict) -> str | None:
    successful = [
        (name, payload)
        for name, payload in models.items()
        if payload.get("status") == "success"
    ]
    if not successful:
        return None

    def sort_key(item):
        metrics = ((item[1].get("metrics") or {}).get("test") or {})
        roc_auc = safe_float(metrics.get("roc_auc"))
        brier = safe_float(metrics.get("brier_score"))
        accuracy = safe_float(metrics.get("accuracy"))
        return (
            -1 if roc_auc is None else roc_auc,
            float("-inf") if brier is None else -brier,
            -1 if accuracy is None else accuracy,
        )

    return max(successful, key=sort_key)[0]


def classify_promotion_readiness(*, target: str, model_result: dict | None) -> dict:
    if not model_result or model_result.get("status") != "success":
        return {
            "status": "not_ready",
            "reason": "no_successful_candidate_model",
        }
    metrics = (model_result.get("metrics") or {}).get("test") or {}
    floor = TARGET_METRIC_SPECS[target]["promotion_floor"]
    checks = []
    if "test_roc_auc" in floor:
        checks.append(compare_floor("roc_auc", metrics.get("roc_auc"), floor["test_roc_auc"]))
    if "test_accuracy" in floor:
        checks.append(compare_floor("accuracy", metrics.get("accuracy"), floor["test_accuracy"]))
    if "large_drop_hit_rate" in floor:
        checks.append(
            {
                "name": "large_drop_hit_rate",
                "status": "manual_review",
                "message": "Large-drop hit rate requires prediction-outcome monitoring, not only static model metrics.",
            }
        )
    failed = [check for check in checks if check["status"] != "pass"]
    return {
        "status": "ready_for_comparison" if not failed else "not_ready",
        "checks": checks,
        "reason": "all_static_checks_passed" if not failed else "static_checks_failed",
    }


def compare_floor(name: str, value: Any, threshold: float) -> dict:
    parsed = safe_float(value)
    if parsed is None:
        return {
            "name": name,
            "status": "manual_review",
            "value": None,
            "threshold": threshold,
            "message": f"{name} is missing.",
        }
    if parsed < threshold:
        return {
            "name": name,
            "status": "reject",
            "value": parsed,
            "threshold": threshold,
            "message": f"{name} is below floor.",
        }
    return {
        "name": name,
        "status": "pass",
        "value": parsed,
        "threshold": threshold,
        "message": f"{name} passes floor.",
    }


def build_candidate_recommendations(report: dict) -> list[str]:
    recommendations = [
        "Do not promote any candidate model without monitoring-outcome and calibration comparison.",
        "Keep news and similar-case features excluded from core candidate training until coverage improves.",
    ]
    if any(
        target.get("promotion_readiness", {}).get("status") == "ready_for_comparison"
        for target in report["targets"].values()
        if isinstance(target, dict)
    ):
        recommendations.append("Run model upgrade review against production metrics for targets that passed static floors.")
    else:
        recommendations.append("Continue feature engineering and calibration before considering promotion.")
    return recommendations


def build_candidate_model_experiment_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 15 Candidate Model Experiment",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Feature policy: `{report['feature_policy']['name']}`",
        f"- Excluded groups: {', '.join(report['feature_policy']['excluded_feature_groups'])}",
        "",
        "## Target Results",
        "",
        "| Target | Status | Best Model | Test Accuracy | Test ROC AUC | Test Brier | Promotion Readiness |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for target, target_result in report["targets"].items():
        best_model = target_result.get("best_model")
        metrics = (
            ((target_result.get("models") or {}).get(best_model) or {})
            .get("metrics", {})
            .get("test", {})
            if best_model
            else {}
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    target_result.get("status", "unknown"),
                    str(best_model or "n/a"),
                    format_float(metrics.get("accuracy")),
                    format_float(metrics.get("roc_auc")),
                    format_float(metrics.get("brier_score")),
                    (target_result.get("promotion_readiness") or {}).get("status", "n/a"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {recommendation}" for recommendation in report["recommendations"])
    return "\n".join(lines) + "\n"


def sample_train_frame(
    frame: pd.DataFrame,
    *,
    max_train_rows: int,
    random_state: int,
) -> pd.DataFrame:
    if max_train_rows <= 0 or len(frame) <= max_train_rows:
        return frame.copy()
    return frame.sample(n=max_train_rows, random_state=random_state).copy()


def predict_probability(model, matrix: pd.DataFrame):
    if hasattr(model, "predict_proba"):
        return model.predict_proba(matrix)[:, 1]
    if hasattr(model, "decision_function"):
        scores = model.decision_function(matrix)
        return 1 / (1 + pd.Series(scores).map(lambda value: pow(2.718281828, -value)))
    return None


def safe_roc_auc(y_true, y_score) -> float | None:
    if y_score is None or y_true.nunique() < 2:
        return None
    return float(roc_auc_score(y_true, y_score))


def safe_brier_score(y_true, y_score) -> float | None:
    if y_score is None:
        return None
    return float(brier_score_loss(y_true, y_score))


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def format_float(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.3f}"
