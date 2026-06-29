import json
import pickle
from pathlib import Path

import pandas as pd

from ml_baseline.trainer import BASELINE_TARGETS, MODEL_VERSION, build_raw_feature_frame


DEFAULT_MODEL_NAME = "random_forest"
USAGE_POLICY = "reference_only"


def build_ml_research_output(
    *,
    feature_row: dict,
    model_dir: str | Path,
    metrics_path: str | Path | None = None,
    dataset_metadata_path: str | Path | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    return_reference: dict | None = None,
    return_model: dict | None = None,
) -> dict:
    metrics = load_baseline_metrics(metrics_path) if metrics_path else {}
    dataset_metadata = load_json(dataset_metadata_path) if dataset_metadata_path else {}
    targets = {}

    for target in BASELINE_TARGETS:
        payload = load_model_payload(
            model_dir=model_dir,
            target=target,
            model_name=model_name,
        )
        probability = predict_probability(feature_row=feature_row, payload=payload)
        targets[target] = build_target_output(
            target=target,
            probability=probability,
            metrics=metrics,
            model_name=model_name,
        )

    return_reference = return_reference or build_empty_return_reference()
    large_drop_probability = targets["large_drop_20d"]["probability"]
    output = {
        "status": "success",
        "usage_policy": USAGE_POLICY,
        "model_version": MODEL_VERSION,
        "model_name": model_name,
        "feature_version": feature_row.get("feature_version"),
        "label_version": feature_row.get("label_version"),
        "training_data_as_of": dataset_metadata.get("data_end_date"),
        "dataset_rows": dataset_metadata.get("row_count"),
        "targets": targets,
        "return_reference": normalize_return_reference(return_reference),
        "return_model": return_model or build_empty_return_model(),
        "risk_note": build_risk_note(large_drop_probability),
        "summary": build_summary(targets),
    }
    return output


def predict_probability(*, feature_row: dict, payload: dict) -> float:
    matrix = build_prediction_matrix(feature_row=feature_row, payload=payload)
    return float(payload["model"].predict_proba(matrix)[0][1])


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


def build_target_output(
    *,
    target: str,
    probability: float,
    metrics: dict,
    model_name: str,
) -> dict:
    test_roc_auc = (
        metrics.get("targets", {})
        .get(target, {})
        .get("models", {})
        .get(model_name, {})
        .get("metrics", {})
        .get("test", {})
        .get("roc_auc")
    )
    return {
        "probability": probability,
        "probability_percent": round(probability * 100, 1),
        "signal_label": classify_signal_label(target, probability),
        "signal_quality": classify_signal_quality(test_roc_auc),
        "model_target": target,
        "model_quality_source": {
            "metric": "test_roc_auc",
            "value": test_roc_auc,
        },
    }


def classify_signal_label(target: str, probability: float) -> str:
    if target == "large_drop_20d":
        if probability >= 0.45:
            return "high large-drop risk"
        if probability >= 0.30:
            return "medium large-drop risk"
        if probability >= 0.18:
            return "low-to-medium large-drop risk"
        return "low large-drop risk"

    if probability >= 0.60:
        return "bullish tilt"
    if probability >= 0.53:
        return "slightly bullish"
    if probability <= 0.40:
        return "bearish tilt"
    if probability <= 0.47:
        return "slightly bearish"
    return "unclear direction"


def classify_signal_quality(test_roc_auc: float | None) -> str:
    if test_roc_auc is None:
        return "unknown"
    if test_roc_auc >= 0.65:
        return "high"
    if test_roc_auc >= 0.58:
        return "medium"
    if test_roc_auc >= 0.53:
        return "low_to_medium"
    return "low"


def normalize_return_reference(return_reference: dict) -> dict:
    output = {
        "method": return_reference.get("method", "historical_reference"),
        "note": return_reference.get(
            "note",
            "Return ranges are historical references, not regression predictions.",
        ),
        "sample_size": return_reference.get("sample_size"),
        "similarity_scope": return_reference.get("similarity_scope"),
        "evidence_quality": return_reference.get("evidence_quality"),
        "reason": return_reference.get("reason"),
    }
    for horizon in ["5d", "10d", "20d"]:
        average_key = f"historical_average_return_{horizon}"
        range_key = f"expected_return_range_{horizon}"
        upside_key = f"upside_return_range_{horizon}"
        output[average_key] = return_reference.get(average_key)
        output[range_key] = normalize_range(return_reference.get(range_key))
        output[upside_key] = normalize_range(return_reference.get(upside_key))
    output["max_drop_range_20d"] = normalize_range(
        return_reference.get("max_drop_range_20d")
    )
    return output


def normalize_range(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {
            "low": value.get("low"),
            "high": value.get("high"),
            "method": value.get("method", "historical_reference"),
        }
    return None


def build_empty_return_reference() -> dict:
    return {
        "method": "historical_reference_pending",
        "note": (
            "Expected return ranges will use historical or similar-case references "
            "before Step 7.8 return models are trained."
        ),
    }


def build_empty_return_model() -> dict:
    return {
        "status": "unavailable",
        "usage_policy": "experimental_reference_only",
        "reason": "return_model_artifacts_missing",
        "summary": "Return model is unavailable. Historical return reference remains the primary range reference.",
    }


def build_risk_note(large_drop_probability: float) -> str:
    percent = round(large_drop_probability * 100, 1)
    label = classify_signal_label("large_drop_20d", large_drop_probability)
    return (
        f"ML baseline estimates 20-day large-drop risk at {percent}% "
        f"({label}). Use this as a risk-control reference only."
    )


def build_summary(targets: dict) -> str:
    up_5d = targets["up_5d"]
    up_10d = targets["up_10d"]
    up_20d = targets["up_20d"]
    large_drop = targets["large_drop_20d"]
    return (
        "ML baseline is a reference-only signal. "
        f"5-day upside probability is {up_5d['probability_percent']}% "
        f"({up_5d['signal_label']}), "
        f"10-day upside probability is {up_10d['probability_percent']}% "
        f"({up_10d['signal_label']}), "
        f"20-day upside probability is {up_20d['probability_percent']}% "
        f"({up_20d['signal_label']}), and "
        f"20-day large-drop risk is {large_drop['probability_percent']}% "
        f"({large_drop['signal_label']})."
    )


def load_model_payload(*, model_dir: str | Path, target: str, model_name: str) -> dict:
    model_path = Path(model_dir) / f"{target}_{model_name}_{MODEL_VERSION}.pkl"
    with model_path.open("rb") as model_file:
        return pickle.load(model_file)


def load_baseline_metrics(metrics_path: str | Path) -> dict:
    return load_json(metrics_path)


def load_json(path: str | Path | None) -> dict:
    if not path:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
