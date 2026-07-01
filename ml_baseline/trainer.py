import json
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml_dataset import FEATURE_COLUMNS
from ml_versions import CLASSIFICATION_MODEL_VERSION


MODEL_VERSION = CLASSIFICATION_MODEL_VERSION
BASELINE_TARGETS = ["up_5d", "up_10d", "up_20d", "large_drop_20d"]
CATEGORICAL_FEATURES = {
    "market_regime": ["bull", "bear", "sideways", "unknown"],
    "similar_case_evidence_quality": [
        "high",
        "medium",
        "low_to_medium",
        "low",
        "none",
        "not_used",
        "unknown",
    ],
}


def train_baseline_models(
    dataset: pd.DataFrame,
    *,
    targets: list[str] | None = None,
    model_version: str = MODEL_VERSION,
    random_state: int = 42,
) -> dict:
    targets = targets or BASELINE_TARGETS
    results = {
        "model_version": model_version,
        "targets": {},
        "models": {},
        "feature_columns": FEATURE_COLUMNS,
    }

    for target in targets:
        if target not in dataset.columns:
            results["targets"][target] = {
                "status": "skipped",
                "reason": "missing_target_column",
            }
            continue

        target_frame = dataset.dropna(subset=[target]).copy()
        if target_frame.empty:
            results["targets"][target] = {
                "status": "skipped",
                "reason": "no_labeled_rows",
            }
            continue

        split_frames = {
            split: target_frame[target_frame["split"] == split].copy()
            for split in ["train", "validation", "test"]
        }
        if split_frames["train"].empty or split_frames["validation"].empty:
            results["targets"][target] = {
                "status": "skipped",
                "reason": "missing_train_or_validation_split",
            }
            continue

        train_target = normalize_target(split_frames["train"][target])
        if train_target.nunique() < 2:
            results["targets"][target] = {
                "status": "skipped",
                "reason": "train_split_has_single_class",
            }
            continue

        matrices = build_feature_matrices(split_frames)
        models = build_models(random_state=random_state)
        target_results = {
            "status": "success",
            "row_counts": {
                split: len(split_frame) for split, split_frame in split_frames.items()
            },
            "positive_rates": {
                split: safe_mean_boolean(split_frame[target])
                for split, split_frame in split_frames.items()
            },
            "models": {},
        }

        rule_predictions = {
            split: rule_based_predictions(split_frame)
            for split, split_frame in split_frames.items()
        }
        target_results["models"]["rule_based"] = evaluate_predictions_by_split(
            split_frames=split_frames,
            target=target,
            predictions_by_split=rule_predictions,
        )

        results["models"].setdefault(target, {})
        for model_name, model in models.items():
            model.fit(matrices["train"], train_target)
            predictions = {
                split: model.predict(matrices[split])
                for split in ["train", "validation", "test"]
                if not matrices[split].empty
            }
            probabilities = {
                split: model.predict_proba(matrices[split])[:, 1]
                for split in ["train", "validation", "test"]
                if not matrices[split].empty
            }
            target_results["models"][model_name] = evaluate_predictions_by_split(
                split_frames=split_frames,
                target=target,
                predictions_by_split=predictions,
                probabilities_by_split=probabilities,
            )
            target_results["models"][model_name]["feature_importance"] = (
                extract_feature_importance(model_name, model, matrices["train"].columns)
            )
            results["models"][target][model_name] = {
                "model": model,
                "feature_columns": list(matrices["train"].columns),
                "numeric_medians": matrices["numeric_medians"],
            }

        results["targets"][target] = target_results

    return results


def build_feature_matrices(split_frames: dict[str, pd.DataFrame]) -> dict:
    train_features = build_raw_feature_frame(split_frames["train"])
    numeric_medians = {
        column: train_features[column].median()
        for column in train_features.columns
        if column not in categorical_dummy_columns()
    }

    matrices = {"numeric_medians": numeric_medians}
    for split, split_frame in split_frames.items():
        features = build_raw_feature_frame(split_frame)
        for column, median in numeric_medians.items():
            features[column] = features[column].fillna(0 if pd.isna(median) else median)
        matrices[split] = features
    return matrices


def build_raw_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    feature_frame = pd.DataFrame(index=frame.index)
    for feature in FEATURE_COLUMNS:
        if feature not in frame.columns:
            continue

        if feature in CATEGORICAL_FEATURES:
            values = frame[feature].fillna("unknown").astype(str)
            for category in CATEGORICAL_FEATURES[feature]:
                feature_frame[f"{feature}__{category}"] = (
                    values == category
                ).astype(int)
            continue

        feature_frame[feature] = normalize_feature_series(frame[feature])

    return feature_frame


def build_models(*, random_state: int) -> dict:
    return {
        "logistic_regression": LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            solver="liblinear",
            random_state=random_state,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=80,
            max_depth=8,
            min_samples_leaf=50,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=random_state,
        ),
    }


def rule_based_predictions(frame: pd.DataFrame) -> pd.Series:
    score = pd.Series(0, index=frame.index, dtype=float)
    score += normalize_feature_series(frame.get("price_vs_ma20", 0)).gt(0).astype(int)
    score += normalize_feature_series(frame.get("price_vs_ma50", 0)).gt(0).astype(int)
    score += normalize_feature_series(frame.get("price_vs_ma200", 0)).gt(0).astype(int)
    score += normalize_feature_series(frame.get("macd_histogram", 0)).gt(0).astype(int)
    score += normalize_feature_series(frame.get("rsi_14", 0)).between(45, 70).astype(int)
    score += frame.get("market_regime", "unknown").eq("bull").astype(int)
    score += frame.get("is_breakout", False).map(to_bool).astype(int)
    return score >= 4


def evaluate_predictions_by_split(
    *,
    split_frames: dict[str, pd.DataFrame],
    target: str,
    predictions_by_split: dict[str, pd.Series],
    probabilities_by_split: dict[str, pd.Series] | None = None,
) -> dict:
    probabilities_by_split = probabilities_by_split or {}
    metrics = {}
    for split, frame in split_frames.items():
        if frame.empty or split not in predictions_by_split:
            continue

        y_true = normalize_target(frame[target])
        y_pred = normalize_target(predictions_by_split[split])
        y_score = probabilities_by_split.get(split)
        metrics[split] = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "roc_auc": safe_roc_auc(y_true, y_score),
            "positive_rate": float(y_true.mean()),
            "predicted_positive_rate": float(y_pred.mean()),
            "rows": int(len(y_true)),
        }
    return {"metrics": metrics}


def extract_feature_importance(model_name: str, model, columns) -> list[dict]:
    if model_name == "logistic_regression":
        values = model.coef_[0]
    elif hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:
        return []

    return sorted(
        [
            {
                "feature": str(column),
                "importance": float(value),
                "absolute_importance": abs(float(value)),
            }
            for column, value in zip(columns, values)
        ],
        key=lambda item: item["absolute_importance"],
        reverse=True,
    )[:30]


def write_baseline_outputs(
    *,
    result: dict,
    report_dir: str | Path,
    model_dir: str | Path,
) -> dict:
    report_dir = Path(report_dir)
    model_dir = Path(model_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = report_dir / "baseline_metrics_v1.json"
    feature_importance_path = report_dir / "baseline_feature_importance_v1.json"
    summary_path = report_dir / "baseline_summary_v1.md"

    serializable_metrics = strip_models(result)
    feature_importance = collect_feature_importance(result)
    metrics_path.write_text(
        json.dumps(serializable_metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    feature_importance_path.write_text(
        json.dumps(feature_importance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(build_summary_markdown(serializable_metrics), encoding="utf-8")

    model_paths = []
    for target, models in result.get("models", {}).items():
        for model_name, payload in models.items():
            path = model_dir / f"{target}_{model_name}_{MODEL_VERSION}.pkl"
            with path.open("wb") as model_file:
                pickle.dump(payload, model_file)
            model_paths.append(str(path))

    return {
        "metrics_path": str(metrics_path),
        "feature_importance_path": str(feature_importance_path),
        "summary_path": str(summary_path),
        "model_paths": model_paths,
    }


def strip_models(result: dict) -> dict:
    return {
        key: value
        for key, value in result.items()
        if key != "models"
    }


def collect_feature_importance(result: dict) -> dict:
    output = {}
    for target, target_result in result.get("targets", {}).items():
        output[target] = {}
        for model_name, model_result in target_result.get("models", {}).items():
            if "feature_importance" in model_result:
                output[target][model_name] = model_result["feature_importance"]
    return output


def build_summary_markdown(result: dict) -> str:
    lines = [
        "# Baseline Model Summary",
        "",
        f"- Model version: `{result['model_version']}`",
        "- Targets: `up_5d`, `up_10d`, `up_20d`, `large_drop_20d`",
        "- Split: time-based train / validation / test from dataset.",
        "",
    ]
    for target, target_result in result.get("targets", {}).items():
        lines.append(f"## {target}")
        if target_result.get("status") != "success":
            lines.append(f"- Status: {target_result.get('status')}")
            lines.append(f"- Reason: {target_result.get('reason')}")
            lines.append("")
            continue

        for model_name, model_result in target_result.get("models", {}).items():
            test_metrics = model_result.get("metrics", {}).get("test", {})
            validation_metrics = model_result.get("metrics", {}).get("validation", {})
            lines.append(
                "- "
                f"{model_name}: validation accuracy "
                f"{format_metric(validation_metrics.get('accuracy'))}, "
                f"test accuracy {format_metric(test_metrics.get('accuracy'))}, "
                f"test ROC AUC {format_metric(test_metrics.get('roc_auc'))}"
            )
        lines.append("")

    lines.append(
        "This baseline report is for model evaluation only and is not investment advice."
    )
    lines.append("")
    return "\n".join(lines)


def normalize_feature_series(series) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(series)
    return series.map(to_number)


def normalize_target(series) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return series.map(to_bool).astype(int)


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_number(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"true", "false"}:
            return 1 if stripped.lower() == "true" else 0
        if stripped == "":
            return None
    return pd.to_numeric(value, errors="coerce")


def safe_mean_boolean(series) -> float | None:
    if series.empty:
        return None
    return float(normalize_target(series).mean())


def safe_roc_auc(y_true, y_score) -> float | None:
    if y_score is None or y_true.nunique() < 2:
        return None
    return float(roc_auc_score(y_true, y_score))


def categorical_dummy_columns() -> set[str]:
    return {
        f"{feature}__{category}"
        for feature, categories in CATEGORICAL_FEATURES.items()
        for category in categories
    }


def format_metric(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"
