from __future__ import annotations

import math
import os
import warnings
from datetime import UTC, datetime
from typing import Any

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    mean_absolute_error,
    precision_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)

from ml_baseline.trainer import build_raw_feature_frame, normalize_target
from ml_model_improvement.candidate_models import CORE_FEATURES, select_core_features


CLASSIFICATION_TARGETS = ("up_5d", "up_10d", "up_20d", "large_drop_20d")
TARGET_HORIZONS = {
    "up_5d": 5,
    "up_10d": 10,
    "up_20d": 20,
    "large_drop_20d": 20,
    "forward_return_5d": 5,
    "forward_return_10d": 10,
    "forward_return_20d": 20,
    "max_drop_20d": 20,
}
REGRESSION_TARGETS = (
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "max_drop_20d",
)
DEFAULT_CLASSIFICATION_MODELS = (
    "logistic_regression",
    "random_forest",
    "extra_trees",
    "xgboost",
    "lightgbm",
)
DEFAULT_REGRESSION_MODELS = (
    "random_forest",
    "hist_gradient_boosting",
    "xgboost",
    "lightgbm",
)
CALIBRATED_MODEL_NAMES = {"logistic_regression", "random_forest", "extra_trees"}


QUALITY_POLICY = {
    "classification": {
        "minimum_fold_rows": 500,
        "minimum_roc_auc": 0.53,
        "minimum_accuracy_delta_vs_naive": 0.01,
        "minimum_brier_improvement_vs_naive": 0.005,
        "maximum_calibration_error": 0.10,
        "minimum_regime_roc_auc": 0.48,
        "minimum_large_drop_recall": 0.80,
        "maximum_large_drop_miss_rate": 0.20,
    },
    "regression": {
        "minimum_fold_rows": 500,
        "minimum_mae_improvement_vs_naive": 0.05,
        "minimum_directional_accuracy": 0.52,
        "minimum_interval_coverage": 0.70,
        "maximum_interval_coverage": 0.95,
        "maximum_downside_underestimation_rate": 0.20,
    },
    "promotion": {
        "selection_fold_count": 2,
        "holdout_fold_count": 1,
        "automatic_replacement": False,
        "required_core_targets": [
            "up_5d",
            "up_10d",
            "up_20d",
            "large_drop_20d",
            "max_drop_20d",
        ],
    },
}


def build_step28_quality_upgrade(
    dataset: pd.DataFrame,
    *,
    classification_models: list[str] | None = None,
    regression_models: list[str] | None = None,
    max_train_rows: int = 60_000,
    max_evaluation_rows: int = 40_000,
    random_state: int = 42,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    prepared = prepare_dataset(dataset)
    folds = build_walk_forward_folds(prepared)
    classification_models = classification_models or list(DEFAULT_CLASSIFICATION_MODELS)
    regression_models = regression_models or list(DEFAULT_REGRESSION_MODELS)

    target_results: dict[str, dict] = {}
    for target in CLASSIFICATION_TARGETS:
        target_results[target] = evaluate_classification_target(
            prepared,
            target=target,
            folds=folds,
            model_names=classification_models,
            max_train_rows=max_train_rows,
            max_evaluation_rows=max_evaluation_rows,
            random_state=random_state,
        )
    for target in REGRESSION_TARGETS:
        target_results[target] = evaluate_regression_target(
            prepared,
            target=target,
            folds=folds,
            model_names=regression_models,
            max_train_rows=max_train_rows,
            max_evaluation_rows=max_evaluation_rows,
            random_state=random_state,
        )

    promotion = build_bundle_promotion(target_results)
    return {
        "report_version": "step28_model_quality_upgrade_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "dataset": {
            "rows": int(len(prepared)),
            "data_start_date": format_date(prepared["_date"].min()),
            "data_end_date": format_date(prepared["_date"].max()),
            "ticker_count": int(prepared["ticker"].nunique()) if "ticker" in prepared else None,
        },
        "evaluation_design": {
            "method": "purged_expanding_walk_forward_with_final_holdout",
            "folds": [public_fold(fold) for fold in folds],
            "model_selection": "selection folds only",
            "promotion_validation": "final holdout fold plus regime stability",
            "label_overlap_policy": "purge each training fold by the target horizon before evaluation",
            "max_train_rows_per_fold": max_train_rows,
            "max_evaluation_rows_per_fold": max_evaluation_rows,
        },
        "quality_policy": QUALITY_POLICY,
        "targets": target_results,
        "promotion": promotion,
        "ml_reference_policy": (
            "candidate_ready_for_manual_review"
            if promotion["status"] == "candidate_bundle_ready"
            else "reduced_trust"
        ),
    }


def reevaluate_step28_report(
    report: dict,
    *,
    generated_at: datetime | None = None,
) -> dict:
    updated = {**report, "quality_policy": QUALITY_POLICY}
    updated_targets = {}
    for target, result in (report.get("targets") or {}).items():
        refreshed = {**result}
        models = result.get("models") or {}
        candidate = models.get(result.get("best_candidate")) or {}
        if result.get("target_type") == "classification":
            quality = classify_classification_quality(
                target=target,
                candidate=candidate,
                baseline=models.get("naive_prevalence") or {},
            )
        elif result.get("target_type") == "regression":
            quality = classify_regression_quality(
                target=target,
                candidate=candidate,
                baseline=models.get("naive_historical_mean") or {},
            )
        else:
            quality = unknown_quality("unknown_target_type")
        refreshed["quality"] = quality
        refreshed["promotion_decision"] = "pass" if quality["promotion_ready"] else "reject"
        updated_targets[target] = refreshed
    updated["targets"] = updated_targets
    updated["promotion"] = build_bundle_promotion(updated_targets)
    updated["ml_reference_policy"] = (
        "candidate_ready_for_manual_review"
        if updated["promotion"]["status"] == "candidate_bundle_ready"
        else "reduced_trust"
    )
    generated = generated_at or datetime.now(UTC)
    updated["policy_reevaluated_at"] = generated.replace(microsecond=0).isoformat()
    return updated


def prepare_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    if "date" not in dataset.columns:
        raise ValueError("dataset requires a date column")
    prepared = dataset.copy()
    prepared["_date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["_date"]).sort_values(["_date", "ticker"])
    if prepared.empty:
        raise ValueError("dataset has no valid dated rows")
    return prepared


def build_walk_forward_folds(dataset: pd.DataFrame) -> list[dict]:
    dates = dataset["_date"]
    predefined = [
        ("2021_2022", "2020-12-31", "2021-01-01", "2022-12-31"),
        ("2023_2024", "2022-12-31", "2023-01-01", "2024-12-31"),
        ("2025_latest", "2024-12-31", "2025-01-01", None),
    ]
    folds = []
    for name, train_end, test_start, test_end in predefined:
        train_mask = dates <= pd.Timestamp(train_end)
        test_mask = dates >= pd.Timestamp(test_start)
        if test_end:
            test_mask &= dates <= pd.Timestamp(test_end)
        if train_mask.any() and test_mask.any():
            folds.append(
                make_fold(
                    name=name,
                    dataset=dataset,
                    train_mask=train_mask,
                    test_mask=test_mask,
                )
            )
    if len(folds) >= 3:
        return folds[-3:]
    return build_quantile_folds(dataset)


def build_quantile_folds(dataset: pd.DataFrame) -> list[dict]:
    unique_dates = pd.Series(dataset["_date"].drop_duplicates().sort_values().tolist())
    if len(unique_dates) < 8:
        raise ValueError("dataset requires at least 8 distinct dates for walk-forward evaluation")
    boundaries = [0.50, 0.65, 0.80, 1.00]
    indices = [min(len(unique_dates) - 1, int(len(unique_dates) * value)) for value in boundaries]
    folds = []
    for index in range(3):
        train_end = unique_dates.iloc[indices[index] - 1]
        test_start = unique_dates.iloc[indices[index]]
        test_end = unique_dates.iloc[indices[index + 1] - 1]
        folds.append(
            make_fold(
                name=f"walk_forward_{index + 1}",
                dataset=dataset,
                train_mask=dataset["_date"] <= train_end,
                test_mask=(dataset["_date"] >= test_start) & (dataset["_date"] <= test_end),
            )
        )
    return folds


def make_fold(*, name: str, dataset: pd.DataFrame, train_mask, test_mask) -> dict:
    train = dataset.loc[train_mask]
    test = dataset.loc[test_mask]
    return {
        "name": name,
        "train_index": train.index,
        "test_index": test.index,
        "train_start": format_date(train["_date"].min()),
        "train_end": format_date(train["_date"].max()),
        "test_start": format_date(test["_date"].min()),
        "test_end": format_date(test["_date"].max()),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "role": "holdout" if name in {"2025_latest", "walk_forward_3"} else "selection",
    }


def public_fold(fold: dict) -> dict:
    return {key: value for key, value in fold.items() if not key.endswith("_index")}


def evaluate_classification_target(
    dataset: pd.DataFrame,
    *,
    target: str,
    folds: list[dict],
    model_names: list[str],
    max_train_rows: int,
    max_evaluation_rows: int,
    random_state: int,
) -> dict:
    if target not in dataset.columns:
        return skipped_target("missing_target_column")
    model_results = {"naive_prevalence": {"status": "success", "folds": []}}
    for name in model_names:
        model_results[name] = {"status": "success", "folds": []}
        if name in CALIBRATED_MODEL_NAMES:
            model_results[f"{name}_calibrated_sigmoid"] = {"status": "success", "folds": []}

    for fold_number, fold in enumerate(folds):
        train, test = target_fold_frames(
            dataset,
            target=target,
            fold=fold,
            max_train_rows=max_train_rows,
            max_evaluation_rows=max_evaluation_rows,
            random_state=random_state + fold_number,
        )
        if train.empty or test.empty or normalize_target(train[target]).nunique() < 2:
            continue
        x_train, x_test = build_feature_pair(train, test)
        y_train = normalize_target(train[target])
        y_test = normalize_target(test[target])
        prevalence = float(y_train.mean())
        naive_probability = pd.Series(prevalence, index=test.index)
        model_results["naive_prevalence"]["folds"].append(
            classification_fold_metrics(
                y_true=y_test,
                probability=naive_probability,
                frame=test,
                fold=fold,
                target=target,
                decision_threshold=0.5,
            )
        )

        for name in model_names:
            model = build_classification_model(name, y_train=y_train, random_state=random_state)
            if model is None:
                model_results[name] = {"status": "skipped", "reason": "dependency_unavailable", "folds": []}
                if name in CALIBRATED_MODEL_NAMES:
                    model_results[f"{name}_calibrated_sigmoid"] = {
                        "status": "skipped",
                        "reason": "dependency_unavailable",
                        "folds": [],
                    }
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(x_train, y_train)
            probability = pd.Series(model.predict_proba(x_test)[:, 1], index=test.index)
            model_results[name]["folds"].append(
                classification_fold_metrics(
                    y_true=y_test,
                    probability=probability,
                    frame=test,
                    fold=fold,
                    target=target,
                    decision_threshold=0.5,
                )
            )
            if name not in CALIBRATED_MODEL_NAMES:
                continue
            calibrated_result = fit_time_ordered_calibrator(
                name=name,
                x_train=x_train,
                y_train=y_train,
                random_state=random_state,
                target=target,
            )
            calibrated_name = f"{name}_calibrated_sigmoid"
            if calibrated_result is None:
                model_results[calibrated_name] = {
                    "status": "skipped",
                    "reason": "calibration_split_unusable",
                    "folds": [],
                }
                continue
            calibrated, decision_threshold = calibrated_result
            calibrated_probability = pd.Series(
                calibrated.predict_proba(x_test)[:, 1],
                index=test.index,
            )
            model_results[calibrated_name]["folds"].append(
                classification_fold_metrics(
                    y_true=y_test,
                    probability=calibrated_probability,
                    frame=test,
                    fold=fold,
                    target=target,
                    decision_threshold=decision_threshold,
                )
            )

    finalize_model_results(model_results, metric_names=classification_metric_names(target))
    best_model = choose_classification_candidate(model_results)
    quality = classify_classification_quality(
        target=target,
        candidate=model_results.get(best_model) or {},
        baseline=model_results["naive_prevalence"],
    )
    return {
        "status": "success" if best_model else "skipped",
        "target_type": "classification",
        "best_candidate": best_model,
        "models": model_results,
        "quality": quality,
        "promotion_decision": "pass" if quality["promotion_ready"] else "reject",
    }


def evaluate_regression_target(
    dataset: pd.DataFrame,
    *,
    target: str,
    folds: list[dict],
    model_names: list[str],
    max_train_rows: int,
    max_evaluation_rows: int,
    random_state: int,
) -> dict:
    if target not in dataset.columns:
        return skipped_target("missing_target_column")
    model_results = {"naive_historical_mean": {"status": "success", "folds": []}}
    for name in model_names:
        model_results[name] = {"status": "success", "folds": []}

    for fold_number, fold in enumerate(folds):
        train, test = target_fold_frames(
            dataset,
            target=target,
            fold=fold,
            max_train_rows=max_train_rows,
            max_evaluation_rows=max_evaluation_rows,
            random_state=random_state + fold_number,
        )
        if train.empty or test.empty:
            continue
        x_train, x_test = build_feature_pair(train, test)
        y_train = pd.to_numeric(train[target], errors="coerce")
        y_test = pd.to_numeric(test[target], errors="coerce")
        low_model, high_model = build_quantile_models(random_state=random_state)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            low_model.fit(x_train, y_train)
            high_model.fit(x_train, y_train)
        low = pd.Series(low_model.predict(x_test), index=test.index)
        high = pd.Series(high_model.predict(x_test), index=test.index)
        interval_low = pd.concat([low, high], axis=1).min(axis=1)
        interval_high = pd.concat([low, high], axis=1).max(axis=1)

        naive_value = float(y_train.mean())
        naive_prediction = pd.Series(naive_value, index=test.index)
        model_results["naive_historical_mean"]["folds"].append(
            regression_fold_metrics(
                y_true=y_test,
                prediction=naive_prediction,
                interval_low=interval_low,
                interval_high=interval_high,
                frame=test,
                fold=fold,
                target=target,
            )
        )
        for name in model_names:
            model = build_regression_model(name, random_state=random_state)
            if model is None:
                model_results[name] = {"status": "skipped", "reason": "dependency_unavailable", "folds": []}
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(x_train, y_train)
            prediction = pd.Series(model.predict(x_test), index=test.index)
            model_results[name]["folds"].append(
                regression_fold_metrics(
                    y_true=y_test,
                    prediction=prediction,
                    interval_low=interval_low,
                    interval_high=interval_high,
                    frame=test,
                    fold=fold,
                    target=target,
                )
            )

    finalize_model_results(model_results, metric_names=regression_metric_names(target))
    best_model = choose_regression_candidate(model_results)
    quality = classify_regression_quality(
        target=target,
        candidate=model_results.get(best_model) or {},
        baseline=model_results["naive_historical_mean"],
    )
    return {
        "status": "success" if best_model else "skipped",
        "target_type": "regression",
        "best_candidate": best_model,
        "models": model_results,
        "quality": quality,
        "promotion_decision": "pass" if quality["promotion_ready"] else "reject",
    }


def target_fold_frames(
    dataset: pd.DataFrame,
    *,
    target: str,
    fold: dict,
    max_train_rows: int,
    max_evaluation_rows: int,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = dataset.loc[fold["train_index"]].dropna(subset=[target]).copy()
    test = dataset.loc[fold["test_index"]].dropna(subset=[target]).copy()
    horizon = TARGET_HORIZONS.get(target, 0)
    if horizon and not test.empty:
        purge_cutoff = test["_date"].min() - pd.offsets.BDay(horizon)
        train = train[train["_date"] < purge_cutoff]
    train = deterministic_sample(train, max_train_rows, random_state)
    test = deterministic_sample(test, max_evaluation_rows, random_state + 101)
    return train, test


def deterministic_sample(frame: pd.DataFrame, limit: int, random_state: int) -> pd.DataFrame:
    if limit <= 0 or len(frame) <= limit:
        return frame
    return frame.sample(n=limit, random_state=random_state).sort_values("_date")


def build_feature_pair(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    x_train = select_core_features(build_raw_feature_frame(train))
    x_test = select_core_features(build_raw_feature_frame(test))
    for column in x_train.columns:
        if column not in x_test:
            x_test[column] = 0
    x_test = x_test[x_train.columns]
    medians = x_train.median(numeric_only=True)
    return x_train.fillna(medians).fillna(0), x_test.fillna(medians).fillna(0)


def build_classification_model(name: str, *, y_train: pd.Series, random_state: int):
    if name == "logistic_regression":
        return LogisticRegression(max_iter=1000, class_weight="balanced", solver="liblinear", random_state=random_state)
    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=120,
            max_depth=10,
            min_samples_leaf=40,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=random_state,
        )
    if name == "extra_trees":
        return ExtraTreesClassifier(
            n_estimators=180,
            max_depth=12,
            min_samples_leaf=40,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=random_state,
        )
    if name == "xgboost":
        try:
            from xgboost import XGBClassifier
        except ImportError:
            return None
        positives = int(y_train.sum())
        negatives = int(len(y_train) - positives)
        return XGBClassifier(
            n_estimators=160,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=negatives / positives if positives else 1.0,
            eval_metric="logloss",
            n_jobs=-1,
            random_state=random_state,
        )
    if name == "lightgbm":
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            return None
        return LGBMClassifier(
            n_estimators=180,
            learning_rate=0.05,
            num_leaves=31,
            class_weight="balanced",
            n_jobs=-1,
            random_state=random_state,
            verbose=-1,
        )
    return None


def fit_time_ordered_calibrator(
    *,
    name: str,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int,
    target: str,
):
    split_at = int(len(x_train) * 0.8)
    if split_at < 100 or len(x_train) - split_at < 50:
        return None
    fit_x = x_train.iloc[:split_at]
    fit_y = y_train.iloc[:split_at]
    calibration_x = x_train.iloc[split_at:]
    calibration_y = y_train.iloc[split_at:]
    if fit_y.nunique() < 2 or calibration_y.nunique() < 2:
        return None
    base_model = build_classification_model(
        name,
        y_train=fit_y,
        random_state=random_state,
    )
    if base_model is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base_model.fit(fit_x, fit_y)
        calibrated = CalibratedClassifierCV(
            estimator=FrozenEstimator(base_model),
            method="sigmoid",
            cv=None,
        )
        calibrated.fit(calibration_x, calibration_y)
    threshold = 0.5
    if target == "large_drop_20d":
        calibration_probability = pd.Series(
            calibrated.predict_proba(calibration_x)[:, 1],
            index=calibration_y.index,
        )
        threshold = choose_recall_threshold(
            calibration_y,
            calibration_probability,
            minimum_recall=QUALITY_POLICY["classification"]["minimum_large_drop_recall"],
        )
    return calibrated, threshold


def choose_recall_threshold(
    y_true: pd.Series,
    probability: pd.Series,
    *,
    minimum_recall: float,
) -> float:
    candidates = sorted({0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50})
    passing = [
        threshold
        for threshold in candidates
        if recall_score(y_true, probability >= threshold, zero_division=0) >= minimum_recall
    ]
    return max(passing) if passing else min(candidates)


def build_regression_model(name: str, *, random_state: int):
    if name == "random_forest":
        return RandomForestRegressor(
            n_estimators=80,
            max_depth=10,
            min_samples_leaf=80,
            n_jobs=-1,
            random_state=random_state,
        )
    if name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(
            max_iter=120,
            max_leaf_nodes=31,
            learning_rate=0.05,
            l2_regularization=0.01,
            random_state=random_state,
        )
    if name == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError:
            return None
        return XGBRegressor(
            n_estimators=180,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="reg:squarederror",
            n_jobs=-1,
            random_state=random_state,
        )
    if name == "lightgbm":
        try:
            from lightgbm import LGBMRegressor
        except ImportError:
            return None
        return LGBMRegressor(
            n_estimators=180,
            learning_rate=0.05,
            num_leaves=31,
            n_jobs=-1,
            random_state=random_state,
            verbose=-1,
        )
    return None


def build_quantile_models(*, random_state: int):
    common = {
        "loss": "quantile",
        "max_iter": 80,
        "max_leaf_nodes": 31,
        "learning_rate": 0.06,
        "l2_regularization": 0.01,
        "random_state": random_state,
    }
    return (
        HistGradientBoostingRegressor(quantile=0.10, **common),
        HistGradientBoostingRegressor(quantile=0.90, **common),
    )


def classification_fold_metrics(
    *,
    y_true: pd.Series,
    probability: pd.Series,
    frame: pd.DataFrame,
    fold: dict,
    target: str,
    decision_threshold: float,
) -> dict:
    prediction = probability >= decision_threshold
    metrics = {
        "fold": fold["name"],
        "role": fold["role"],
        "rows": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, prediction)),
        "precision": float(precision_score(y_true, prediction, zero_division=0)),
        "recall": float(recall_score(y_true, prediction, zero_division=0)),
        "roc_auc": safe_roc_auc(y_true, probability),
        "brier_score": float(brier_score_loss(y_true, probability)),
        "calibration_error": expected_calibration_error(y_true, probability),
        "positive_rate": float(y_true.mean()),
        "decision_threshold": decision_threshold,
        "regime_metrics": classification_regime_metrics(frame, y_true, probability),
    }
    if target == "large_drop_20d":
        metrics["downside_miss_rate"] = 1.0 - metrics["recall"]
    return metrics


def regression_fold_metrics(
    *,
    y_true: pd.Series,
    prediction: pd.Series,
    interval_low: pd.Series,
    interval_high: pd.Series,
    frame: pd.DataFrame,
    fold: dict,
    target: str,
) -> dict:
    metrics = {
        "fold": fold["name"],
        "role": fold["role"],
        "rows": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, prediction)),
        "rmse": float(root_mean_squared_error(y_true, prediction)),
        "interval_coverage": float(((y_true >= interval_low) & (y_true <= interval_high)).mean()),
        "average_interval_width": float((interval_high - interval_low).mean()),
        "regime_metrics": regression_regime_metrics(frame, y_true, prediction),
    }
    if target == "max_drop_20d":
        metrics["downside_underestimation_rate"] = float((prediction > y_true).mean())
        metrics["directional_accuracy"] = None
    else:
        metrics["directional_accuracy"] = float(((prediction > 0) == (y_true > 0)).mean())
        downside = y_true < 0
        metrics["downside_underestimation_rate"] = (
            float((prediction[downside] > y_true[downside]).mean()) if downside.any() else None
        )
    return metrics


def classification_regime_metrics(frame, y_true, probability) -> dict:
    if "market_regime" not in frame:
        return {}
    output = {}
    for regime, index in frame.groupby(frame["market_regime"].fillna("unknown")).groups.items():
        labels = y_true.loc[index]
        scores = probability.loc[index]
        output[str(regime)] = {
            "rows": int(len(index)),
            "accuracy": float(accuracy_score(labels, scores >= 0.5)),
            "roc_auc": safe_roc_auc(labels, scores),
        }
    return output


def regression_regime_metrics(frame, y_true, prediction) -> dict:
    if "market_regime" not in frame:
        return {}
    output = {}
    for regime, index in frame.groupby(frame["market_regime"].fillna("unknown")).groups.items():
        labels = y_true.loc[index]
        values = prediction.loc[index]
        output[str(regime)] = {
            "rows": int(len(index)),
            "mae": float(mean_absolute_error(labels, values)),
        }
    return output


def finalize_model_results(model_results: dict, *, metric_names: list[str]) -> None:
    for payload in model_results.values():
        folds = payload.get("folds") or []
        if payload.get("status") != "success" or not folds:
            continue
        payload["selection_metrics"] = aggregate_folds(
            [fold for fold in folds if fold["role"] == "selection"], metric_names
        )
        holdout = [fold for fold in folds if fold["role"] == "holdout"]
        payload["holdout_metrics"] = holdout[-1] if holdout else folds[-1]
        payload["all_fold_metrics"] = aggregate_folds(folds, metric_names)


def aggregate_folds(folds: list[dict], metric_names: list[str]) -> dict:
    if not folds:
        return {}
    output = {"fold_count": len(folds), "rows": sum(fold.get("rows", 0) for fold in folds)}
    for metric in metric_names:
        values = [safe_float(fold.get(metric)) for fold in folds]
        values = [value for value in values if value is not None]
        output[metric] = float(sum(values) / len(values)) if values else None
    return output


def choose_classification_candidate(model_results: dict) -> str | None:
    candidates = successful_candidates(model_results, exclude={"naive_prevalence"})
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda name: classification_selection_score(model_results[name].get("selection_metrics") or {}),
    )


def choose_regression_candidate(model_results: dict) -> str | None:
    candidates = successful_candidates(model_results, exclude={"naive_historical_mean"})
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda name: safe_float((model_results[name].get("selection_metrics") or {}).get("mae")) or math.inf,
    )


def successful_candidates(model_results: dict, *, exclude: set[str]) -> list[str]:
    return [
        name
        for name, payload in model_results.items()
        if name not in exclude
        and payload.get("status") == "success"
        and payload.get("selection_metrics")
        and payload.get("holdout_metrics")
    ]


def classification_selection_score(metrics: dict) -> float:
    auc = safe_float(metrics.get("roc_auc")) or 0.0
    accuracy = safe_float(metrics.get("accuracy")) or 0.0
    brier = safe_float(metrics.get("brier_score")) or 1.0
    calibration = safe_float(metrics.get("calibration_error")) or 1.0
    return auc + accuracy - brier - calibration


def classify_classification_quality(*, target: str, candidate: dict, baseline: dict) -> dict:
    if not candidate.get("holdout_metrics") or not baseline.get("holdout_metrics"):
        return unknown_quality("missing_holdout_metrics")
    policy = QUALITY_POLICY["classification"]
    holdout = candidate["holdout_metrics"]
    baseline_holdout = baseline["holdout_metrics"]
    checks = [
        minimum_check("holdout_rows", holdout.get("rows"), policy["minimum_fold_rows"]),
        minimum_check("holdout_roc_auc", holdout.get("roc_auc"), policy["minimum_roc_auc"]),
        minimum_check(
            "brier_improvement_vs_naive",
            subtract(baseline_holdout.get("brier_score"), holdout.get("brier_score")),
            policy["minimum_brier_improvement_vs_naive"],
        ),
        maximum_check("calibration_error", holdout.get("calibration_error"), policy["maximum_calibration_error"]),
        walk_forward_classification_check(candidate.get("folds") or []),
        regime_classification_check(holdout.get("regime_metrics") or {}, policy["minimum_regime_roc_auc"]),
    ]
    if target == "large_drop_20d":
        checks.extend(
            [
                minimum_check("large_drop_recall", holdout.get("recall"), policy["minimum_large_drop_recall"]),
                maximum_check("large_drop_miss_rate", holdout.get("downside_miss_rate"), policy["maximum_large_drop_miss_rate"]),
            ]
        )
    else:
        checks.append(
            minimum_check(
                "accuracy_delta_vs_naive",
                subtract(holdout.get("accuracy"), baseline_holdout.get("accuracy")),
                policy["minimum_accuracy_delta_vs_naive"],
            )
        )
    return finish_quality(checks, strong_metric=holdout.get("roc_auc"), strong_threshold=0.65)


def classify_regression_quality(*, target: str, candidate: dict, baseline: dict) -> dict:
    if not candidate.get("holdout_metrics") or not baseline.get("holdout_metrics"):
        return unknown_quality("missing_holdout_metrics")
    policy = QUALITY_POLICY["regression"]
    holdout = candidate["holdout_metrics"]
    baseline_holdout = baseline["holdout_metrics"]
    baseline_mae = safe_float(baseline_holdout.get("mae"))
    candidate_mae = safe_float(holdout.get("mae"))
    improvement = (
        (baseline_mae - candidate_mae) / baseline_mae
        if baseline_mae and candidate_mae is not None
        else None
    )
    checks = [
        minimum_check("holdout_rows", holdout.get("rows"), policy["minimum_fold_rows"]),
        minimum_check("mae_improvement_vs_naive", improvement, policy["minimum_mae_improvement_vs_naive"]),
        minimum_check("interval_coverage", holdout.get("interval_coverage"), policy["minimum_interval_coverage"]),
        maximum_check("interval_coverage_upper_bound", holdout.get("interval_coverage"), policy["maximum_interval_coverage"]),
        walk_forward_regression_check(
            candidate.get("folds") or [],
            baseline.get("folds") or [],
        ),
        regime_regression_check(
            holdout.get("regime_metrics") or {},
            baseline_holdout.get("regime_metrics") or {},
        ),
    ]
    if target == "max_drop_20d":
        checks.append(
            maximum_check(
                "downside_underestimation_rate",
                holdout.get("downside_underestimation_rate"),
                policy["maximum_downside_underestimation_rate"],
            )
        )
    else:
        checks.append(
            minimum_check(
                "directional_accuracy",
                holdout.get("directional_accuracy"),
                policy["minimum_directional_accuracy"],
            )
        )
    return finish_quality(checks, strong_metric=improvement, strong_threshold=0.15)


def finish_quality(checks: list[dict], *, strong_metric: Any, strong_threshold: float) -> dict:
    promotion_ready = all(check["status"] == "pass" for check in checks)
    pass_count = sum(check["status"] == "pass" for check in checks)
    if promotion_ready and (safe_float(strong_metric) or 0) >= strong_threshold:
        level = "high"
    elif promotion_ready:
        level = "medium"
    elif pass_count >= max(2, len(checks) - 2):
        level = "low_to_medium"
    else:
        level = "low"
    return {
        "level": level,
        "promotion_ready": promotion_ready,
        "checks": checks,
        "failed_checks": [check["name"] for check in checks if check["status"] != "pass"],
    }


def minimum_check(name: str, value: Any, threshold: float) -> dict:
    parsed = safe_float(value)
    return metric_check(name, parsed, threshold, "minimum", parsed is not None and parsed >= threshold)


def maximum_check(name: str, value: Any, threshold: float) -> dict:
    parsed = safe_float(value)
    return metric_check(name, parsed, threshold, "maximum", parsed is not None and parsed <= threshold)


def metric_check(name: str, value: float | None, threshold: float, direction: str, passed: bool) -> dict:
    return {
        "name": name,
        "status": "pass" if passed else "reject",
        "value": value,
        "threshold": threshold,
        "direction": direction,
    }


def regime_classification_check(regimes: dict, minimum_auc: float) -> dict:
    usable = [
        payload
        for payload in regimes.values()
        if payload.get("rows", 0) >= 200 and safe_float(payload.get("roc_auc")) is not None
    ]
    passed = bool(usable) and all(payload["roc_auc"] >= minimum_auc for payload in usable)
    return {
        "name": "market_regime_stability",
        "status": "pass" if passed else "reject",
        "value": {key: value for key, value in regimes.items() if value.get("rows", 0) >= 200},
        "threshold": minimum_auc,
        "direction": "minimum_roc_auc_per_usable_regime",
    }


def walk_forward_classification_check(folds: list[dict]) -> dict:
    usable = [fold for fold in folds if safe_float(fold.get("roc_auc")) is not None]
    minimum_auc = min((fold["roc_auc"] for fold in usable), default=None)
    passed = len(usable) >= 3 and minimum_auc is not None and minimum_auc >= 0.50
    return {
        "name": "walk_forward_stability",
        "status": "pass" if passed else "reject",
        "value": {fold["fold"]: fold.get("roc_auc") for fold in usable},
        "threshold": 0.50,
        "direction": "minimum_roc_auc_across_folds",
    }


def walk_forward_regression_check(candidate_folds: list[dict], baseline_folds: list[dict]) -> dict:
    baseline_by_fold = {fold.get("fold"): fold for fold in baseline_folds}
    improvements = {}
    for fold in candidate_folds:
        baseline = baseline_by_fold.get(fold.get("fold")) or {}
        candidate_mae = safe_float(fold.get("mae"))
        baseline_mae = safe_float(baseline.get("mae"))
        if candidate_mae is None or not baseline_mae:
            continue
        improvements[str(fold.get("fold"))] = (baseline_mae - candidate_mae) / baseline_mae
    passed = len(improvements) >= 3 and all(value >= -0.05 for value in improvements.values())
    return {
        "name": "walk_forward_stability",
        "status": "pass" if passed else "reject",
        "value": improvements,
        "threshold": -0.05,
        "direction": "minimum_mae_improvement_across_folds",
    }


def regime_regression_check(candidate: dict, baseline: dict) -> dict:
    improvements = {}
    for regime, values in candidate.items():
        baseline_values = baseline.get(regime) or {}
        if values.get("rows", 0) < 200:
            continue
        candidate_mae = safe_float(values.get("mae"))
        baseline_mae = safe_float(baseline_values.get("mae"))
        if candidate_mae is None or not baseline_mae:
            continue
        improvements[regime] = (baseline_mae - candidate_mae) / baseline_mae
    passed = bool(improvements) and all(value >= -0.05 for value in improvements.values())
    return {
        "name": "market_regime_stability",
        "status": "pass" if passed else "reject",
        "value": improvements,
        "threshold": -0.05,
        "direction": "minimum_mae_improvement_per_usable_regime",
    }


def build_bundle_promotion(target_results: dict) -> dict:
    required = QUALITY_POLICY["promotion"]["required_core_targets"]
    target_decisions = {
        target: (target_results.get(target) or {}).get("promotion_decision", "missing")
        for target in required
    }
    ready = all(value == "pass" for value in target_decisions.values())
    passed_targets = [target for target, result in target_results.items() if result.get("promotion_decision") == "pass"]
    status = (
        "candidate_bundle_ready"
        if ready
        else "partial_candidate_ready" if passed_targets else "do_not_promote"
    )
    return {
        "status": status,
        "automatic_replacement": False,
        "target_decisions": target_decisions,
        "passed_targets": passed_targets,
        "blocked_targets": [target for target, value in target_decisions.items() if value != "pass"],
        "action": (
            "manual approval and persisted candidate artifacts are required before replacement"
            if ready
            else "start target-level shadow validation for passed targets; keep other production targets"
            if passed_targets
            else "keep current production models and reduced_trust policy"
        ),
    }


def expected_calibration_error(y_true: pd.Series, probability: pd.Series, bins: int = 10) -> float:
    frame = pd.DataFrame({"label": y_true.astype(float), "probability": probability.astype(float)})
    frame["bucket"] = pd.cut(frame["probability"], bins=[index / bins for index in range(bins + 1)], include_lowest=True)
    total = len(frame)
    error = 0.0
    for _, group in frame.groupby("bucket", observed=True):
        error += len(group) / total * abs(group["probability"].mean() - group["label"].mean())
    return float(error)


def safe_roc_auc(y_true: pd.Series, probability: pd.Series) -> float | None:
    return float(roc_auc_score(y_true, probability)) if y_true.nunique() >= 2 else None


def classification_metric_names(target: str) -> list[str]:
    names = ["accuracy", "precision", "recall", "roc_auc", "brier_score", "calibration_error"]
    return names + (["downside_miss_rate"] if target == "large_drop_20d" else [])


def regression_metric_names(target: str) -> list[str]:
    return ["mae", "rmse", "directional_accuracy", "interval_coverage", "downside_underestimation_rate"]


def skipped_target(reason: str) -> dict:
    return {
        "status": "skipped",
        "reason": reason,
        "quality": unknown_quality(reason),
        "promotion_decision": "reject",
    }


def unknown_quality(reason: str) -> dict:
    return {"level": "unknown", "promotion_ready": False, "checks": [], "failed_checks": [reason]}


def subtract(left: Any, right: Any) -> float | None:
    left_value = safe_float(left)
    right_value = safe_float(right)
    return left_value - right_value if left_value is not None and right_value is not None else None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def format_date(value: Any) -> str | None:
    return value.date().isoformat() if value is not None and not pd.isna(value) else None


def build_step28_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 28 ML Model Quality Upgrade",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Evaluation: `{report['evaluation_design']['method']}`",
        f"- Dataset: `{report['dataset']['rows']}` rows / `{report['dataset']['ticker_count']}` tickers",
        f"- Promotion status: `{report['promotion']['status']}`",
        f"- ML Reference policy: `{report['ml_reference_policy']}`",
        "",
        "## Target Results",
        "",
        "| Target | Type | Best Candidate | Quality | Promotion | Failed Checks |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for target, result in report["targets"].items():
        quality = result.get("quality") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    result.get("target_type", "n/a"),
                    str(result.get("best_candidate") or "n/a"),
                    quality.get("level", "unknown"),
                    result.get("promotion_decision", "reject"),
                    ", ".join(quality.get("failed_checks") or []) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Promotion Decision",
            "",
            f"- Passed targets: {', '.join(report['promotion']['passed_targets']) or 'none'}",
            f"- Blocked targets: {', '.join(report['promotion']['blocked_targets']) or 'none'}",
            f"- Action: {report['promotion']['action']}",
            "- Candidate models never replace production automatically.",
            "",
        ]
    )
    return "\n".join(lines)
