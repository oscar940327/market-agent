import json
import os
import pickle
from pathlib import Path

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from ml_baseline.trainer import build_raw_feature_frame
from ml_dataset import FEATURE_COLUMNS
from ml_versions import RETURN_MODEL_VERSION as CURRENT_RETURN_MODEL_VERSION


RETURN_MODEL_VERSION = CURRENT_RETURN_MODEL_VERSION
RETURN_MODEL_TARGETS = [
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "max_drop_20d",
]


def train_return_models(
    dataset: pd.DataFrame,
    *,
    targets: list[str] | None = None,
    model_version: str = RETURN_MODEL_VERSION,
    random_state: int = 42,
    max_train_rows: int = 120000,
) -> dict:
    targets = targets or RETURN_MODEL_TARGETS
    result = {
        "model_version": model_version,
        "targets": {},
        "models": {},
        "feature_columns": FEATURE_COLUMNS,
    }

    split_frames = {
        split: dataset[dataset["split"] == split].copy()
        for split in ["train", "validation", "test"]
    }
    matrices = build_feature_matrices(split_frames)

    for target in targets:
        if target not in dataset.columns:
            result["targets"][target] = {
                "status": "skipped",
                "reason": "missing_target_column",
            }
            continue

        target_frames = {
            split: frame.dropna(subset=[target]).copy()
            for split, frame in split_frames.items()
        }
        if target_frames["train"].empty or target_frames["validation"].empty:
            result["targets"][target] = {
                "status": "skipped",
                "reason": "missing_train_or_validation_split",
            }
            continue

        model_bundle = build_models(random_state=random_state)
        train_frame = limit_training_rows(
            target_frames["train"],
            max_rows=max_train_rows,
            random_state=random_state,
        )
        train_index = train_frame.index
        y_train = pd.to_numeric(train_frame[target], errors="coerce")
        x_train = matrices["train"].loc[train_index]

        for model in model_bundle.values():
            model.fit(x_train, y_train)

        target_result = {
            "status": "success",
            "row_counts": {
                split: len(frame) for split, frame in target_frames.items()
            },
            "training_row_count_used": int(len(train_frame)),
            "models": {
                "random_forest_regressor": evaluate_point_model(
                    target=target,
                    model=model_bundle["point"],
                    matrices=matrices,
                    split_frames=target_frames,
                ),
                "quantile_regressor": evaluate_quantile_models(
                    target=target,
                    low_model=model_bundle["q25"],
                    high_model=model_bundle["q75"],
                    matrices=matrices,
                    split_frames=target_frames,
                ),
            },
        }
        target_result["models"]["random_forest_regressor"]["feature_importance"] = (
            extract_feature_importance(model_bundle["point"], matrices["train"].columns)
        )
        result["targets"][target] = target_result
        result["models"][target] = {
            "point": {
                "model": model_bundle["point"],
                "feature_columns": list(matrices["train"].columns),
                "numeric_medians": matrices["numeric_medians"],
            },
            "q25": {
                "model": model_bundle["q25"],
                "feature_columns": list(matrices["train"].columns),
                "numeric_medians": matrices["numeric_medians"],
            },
            "q75": {
                "model": model_bundle["q75"],
                "feature_columns": list(matrices["train"].columns),
                "numeric_medians": matrices["numeric_medians"],
            },
        }

    return result


def build_feature_matrices(split_frames: dict[str, pd.DataFrame]) -> dict:
    train_features = build_raw_feature_frame(split_frames["train"])
    numeric_medians = {
        column: train_features[column].median()
        for column in train_features.columns
    }

    matrices = {"numeric_medians": numeric_medians}
    for split, split_frame in split_frames.items():
        features = build_raw_feature_frame(split_frame)
        for column in train_features.columns:
            if column not in features.columns:
                features[column] = 0
        for column, median in numeric_medians.items():
            features[column] = features[column].fillna(0 if pd.isna(median) else median)
        matrices[split] = features[list(train_features.columns)]
    return matrices


def build_models(*, random_state: int) -> dict:
    return {
        "point": RandomForestRegressor(
            n_estimators=35,
            max_depth=8,
            min_samples_leaf=150,
            n_jobs=1,
            random_state=random_state,
        ),
        "q25": HistGradientBoostingRegressor(
            loss="quantile",
            quantile=0.25,
            max_iter=40,
            max_leaf_nodes=31,
            learning_rate=0.08,
            l2_regularization=0.01,
            random_state=random_state,
        ),
        "q75": HistGradientBoostingRegressor(
            loss="quantile",
            quantile=0.75,
            max_iter=40,
            max_leaf_nodes=31,
            learning_rate=0.08,
            l2_regularization=0.01,
            random_state=random_state,
        ),
    }


def limit_training_rows(
    frame: pd.DataFrame,
    *,
    max_rows: int,
    random_state: int,
) -> pd.DataFrame:
    if max_rows <= 0 or len(frame) <= max_rows:
        return frame
    return frame.sample(n=max_rows, random_state=random_state).sort_index()


def evaluate_point_model(
    *,
    target: str,
    model,
    matrices: dict,
    split_frames: dict[str, pd.DataFrame],
) -> dict:
    metrics = {}
    for split, frame in split_frames.items():
        if frame.empty:
            continue
        x_data = matrices[split].loc[frame.index]
        y_true = pd.to_numeric(frame[target], errors="coerce")
        y_pred = pd.Series(model.predict(x_data), index=frame.index)
        metrics[split] = {
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(root_mean_squared_error(y_true, y_pred)),
            "directional_accuracy": directional_accuracy(y_true, y_pred, target),
            "downside_underestimation_rate": downside_underestimation_rate(
                y_true,
                y_pred,
                target,
            ),
            "rows": int(len(frame)),
        }
    return {"metrics": metrics}


def evaluate_quantile_models(
    *,
    target: str,
    low_model,
    high_model,
    matrices: dict,
    split_frames: dict[str, pd.DataFrame],
) -> dict:
    metrics = {}
    for split, frame in split_frames.items():
        if frame.empty:
            continue
        x_data = matrices[split].loc[frame.index]
        y_true = pd.to_numeric(frame[target], errors="coerce")
        low = pd.Series(low_model.predict(x_data), index=frame.index)
        high = pd.Series(high_model.predict(x_data), index=frame.index)
        low, high = normalize_interval(low, high)
        metrics[split] = {
            "coverage": float(((y_true >= low) & (y_true <= high)).mean()),
            "average_interval_width": float((high - low).mean()),
            "downside_underestimation_rate": downside_underestimation_rate(
                y_true,
                low,
                target,
            ),
            "rows": int(len(frame)),
        }
    return {"metrics": metrics}


def normalize_interval(low: pd.Series, high: pd.Series) -> tuple[pd.Series, pd.Series]:
    normalized_low = pd.concat([low, high], axis=1).min(axis=1)
    normalized_high = pd.concat([low, high], axis=1).max(axis=1)
    return normalized_low, normalized_high


def directional_accuracy(y_true: pd.Series, y_pred: pd.Series, target: str) -> float | None:
    if target == "max_drop_20d":
        return None
    return float(((y_true > 0) == (y_pred > 0)).mean())


def downside_underestimation_rate(
    y_true: pd.Series,
    y_pred: pd.Series,
    target: str,
) -> float | None:
    if target == "max_drop_20d":
        return float((y_pred > y_true).mean())
    downside_rows = y_true < 0
    if not downside_rows.any():
        return None
    return float((y_pred[downside_rows] > y_true[downside_rows]).mean())


def extract_feature_importance(model, columns) -> list[dict]:
    if not hasattr(model, "feature_importances_"):
        return []
    return sorted(
        [
            {
                "feature": str(column),
                "importance": float(value),
                "absolute_importance": abs(float(value)),
            }
            for column, value in zip(columns, model.feature_importances_)
        ],
        key=lambda item: item["absolute_importance"],
        reverse=True,
    )[:30]


def write_return_model_outputs(
    *,
    result: dict,
    report_dir: str | Path,
    model_dir: str | Path,
) -> dict:
    report_dir = Path(report_dir)
    model_dir = Path(model_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = report_dir / "return_model_metrics_v1.json"
    feature_importance_path = report_dir / "return_model_feature_importance_v1.json"
    summary_path = report_dir / "return_model_summary_v1.md"
    serializable_metrics = strip_models(result)
    metrics_path.write_text(
        json.dumps(serializable_metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    feature_importance_path.write_text(
        json.dumps(collect_feature_importance(result), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(build_summary_markdown(serializable_metrics), encoding="utf-8")

    model_paths = []
    for target, models in result.get("models", {}).items():
        for model_key, payload in models.items():
            path = model_dir / f"{target}_{model_key}_{RETURN_MODEL_VERSION}.pkl"
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
    return {key: value for key, value in result.items() if key != "models"}


def collect_feature_importance(result: dict) -> dict:
    output = {}
    for target, target_result in result.get("targets", {}).items():
        output[target] = target_result.get("models", {}).get(
            "random_forest_regressor",
            {},
        ).get("feature_importance", [])
    return output


def build_summary_markdown(result: dict) -> str:
    lines = [
        "# Return Model Summary",
        "",
        f"- Model version: `{result['model_version']}`",
        "- Usage: experimental reference only.",
        "",
    ]
    for target, target_result in result.get("targets", {}).items():
        lines.append(f"## {target}")
        if target_result.get("status") != "success":
            lines.append(f"- Status: {target_result.get('status')}")
            lines.append("")
            continue
        point_metrics = (
            target_result["models"]["random_forest_regressor"]["metrics"].get("test", {})
        )
        quantile_metrics = (
            target_result["models"]["quantile_regressor"]["metrics"].get("test", {})
        )
        lines.append(f"- Test MAE: {format_metric(point_metrics.get('mae'))}")
        lines.append(f"- Test RMSE: {format_metric(point_metrics.get('rmse'))}")
        lines.append(
            f"- Test directional accuracy: "
            f"{format_metric(point_metrics.get('directional_accuracy'))}"
        )
        lines.append(
            f"- Test interval coverage: {format_metric(quantile_metrics.get('coverage'))}"
        )
        lines.append("")
    lines.append("These return models are experimental references, not trading advice.")
    lines.append("")
    return "\n".join(lines)


def format_metric(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
