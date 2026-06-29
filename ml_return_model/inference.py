import json
import pickle
from pathlib import Path

import pandas as pd

from ml_baseline.trainer import build_raw_feature_frame
from ml_return_model.trainer import RETURN_MODEL_TARGETS, RETURN_MODEL_VERSION


def build_return_model_output(
    *,
    feature_row: dict,
    model_dir: str | Path,
    metrics_path: str | Path | None = None,
) -> dict:
    metrics = load_json(metrics_path) if metrics_path else {}
    targets = {}
    for target in RETURN_MODEL_TARGETS:
        point_payload = load_model_payload(
            model_dir=model_dir,
            target=target,
            model_key="point",
        )
        low_payload = load_model_payload(
            model_dir=model_dir,
            target=target,
            model_key="q25",
        )
        high_payload = load_model_payload(
            model_dir=model_dir,
            target=target,
            model_key="q75",
        )
        predicted_value = predict_value(feature_row=feature_row, payload=point_payload)
        low = predict_value(feature_row=feature_row, payload=low_payload)
        high = predict_value(feature_row=feature_row, payload=high_payload)
        low, high = min(low, high), max(low, high)
        targets[target] = {
            "predicted_value": predicted_value,
            "predicted_percent": round(predicted_value * 100, 1),
            "predicted_range": {
                "low": low,
                "high": high,
                "low_percent": round(low * 100, 1),
                "high_percent": round(high * 100, 1),
            },
            "model_quality": classify_return_model_quality(target, metrics),
            "metrics": extract_target_metrics(target, metrics),
        }

    return {
        "status": "success",
        "usage_policy": "experimental_reference_only",
        "model_version": RETURN_MODEL_VERSION,
        "model_name": "random_forest_regressor + quantile_gradient_boosting",
        "targets": targets,
        "summary": build_return_model_summary(targets),
    }


def predict_value(*, feature_row: dict, payload: dict) -> float:
    matrix = build_prediction_matrix(feature_row=feature_row, payload=payload)
    return float(payload["model"].predict(matrix)[0])


def build_prediction_matrix(*, feature_row: dict, payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame([feature_row])
    matrix = build_raw_feature_frame(frame)
    feature_columns = payload["feature_columns"]
    numeric_medians = payload.get("numeric_medians", {})
    for column in feature_columns:
        if column not in matrix.columns:
            matrix[column] = 0
    for column, median in numeric_medians.items():
        if column in matrix.columns:
            matrix[column] = matrix[column].fillna(0 if pd.isna(median) else median)
    return matrix[feature_columns]


def classify_return_model_quality(target: str, metrics: dict) -> str:
    test_metrics = (
        metrics.get("targets", {})
        .get(target, {})
        .get("models", {})
        .get("random_forest_regressor", {})
        .get("metrics", {})
        .get("test", {})
    )
    mae = test_metrics.get("mae")
    if mae is None:
        return "unknown"
    if mae <= 0.035:
        return "medium"
    if mae <= 0.055:
        return "low_to_medium"
    return "low"


def extract_target_metrics(target: str, metrics: dict) -> dict:
    target_metrics = metrics.get("targets", {}).get(target, {}).get("models", {})
    return {
        "point_model": target_metrics.get("random_forest_regressor", {}).get(
            "metrics",
            {},
        ).get("test", {}),
        "range_model": target_metrics.get("quantile_regressor", {}).get(
            "metrics",
            {},
        ).get("test", {}),
    }


def build_return_model_summary(targets: dict) -> str:
    return (
        "Return model is experimental. "
        f"Predicted 5d return is {targets['forward_return_5d']['predicted_percent']}%, "
        f"10d return is {targets['forward_return_10d']['predicted_percent']}%, "
        f"20d return is {targets['forward_return_20d']['predicted_percent']}%, and "
        f"20d max-drop estimate is {targets['max_drop_20d']['predicted_percent']}%."
    )


def load_model_payload(*, model_dir: str | Path, target: str, model_key: str) -> dict:
    path = Path(model_dir) / f"{target}_{model_key}_{RETURN_MODEL_VERSION}.pkl"
    with path.open("rb") as model_file:
        return pickle.load(model_file)


def load_json(path: str | Path | None) -> dict:
    if not path:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
