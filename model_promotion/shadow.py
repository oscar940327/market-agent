from __future__ import annotations

import warnings
from datetime import date

import pandas as pd

from ml_baseline.trainer import build_raw_feature_frame, normalize_target
from ml_model_improvement.candidate_models import select_core_features
from ml_model_improvement.quality_upgrade import (
    CLASSIFICATION_TARGETS,
    REGRESSION_TARGETS,
    build_classification_model,
    build_feature_pair,
    build_quantile_models,
    build_regression_model,
    fit_time_ordered_calibrator,
)
from ml_versions import DATASET_VERSION, FEATURE_VERSION


def train_shadow_candidate_models(
    dataset: pd.DataFrame,
    *,
    step28_report: dict,
    candidate_version: str,
    random_state: int = 42,
    max_train_rows: int = 100_000,
) -> dict:
    promotion = step28_report.get("promotion") or {}
    if promotion.get("status") != "candidate_bundle_ready":
        return {
            "status": "skipped",
            "reason": "candidate_bundle_not_ready",
            "candidate_version": candidate_version,
            "models": {},
        }

    frame = dataset.copy()
    frame["_date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["_date"]).sort_values(["_date", "ticker"])
    models = {}
    for target, result in (step28_report.get("targets") or {}).items():
        if target not in frame or result.get("promotion_decision") != "pass":
            continue
        model_name = result.get("best_candidate")
        target_frame = frame.dropna(subset=[target]).copy()
        if len(target_frame) > max_train_rows:
            target_frame = target_frame.tail(max_train_rows)
        if result.get("target_type") == "classification":
            payload = train_classification_payload(
                target_frame,
                target=target,
                model_name=model_name,
                random_state=random_state,
            )
        elif result.get("target_type") == "regression":
            payload = train_regression_payload(
                target_frame,
                target=target,
                model_name=model_name,
                random_state=random_state,
            )
        else:
            payload = None
        if payload:
            models[target] = payload

    required = set(promotion.get("passed_targets") or [])
    missing = sorted(required - set(models))
    status = "success" if models and not missing else "failed"
    return {
        "status": status,
        "reason": None if status == "success" else "candidate_model_training_incomplete",
        "candidate_version": candidate_version,
        "feature_version": FEATURE_VERSION,
        "dataset_version": DATASET_VERSION,
        "models": models,
        "trained_targets": sorted(models),
        "missing_targets": missing,
    }


def train_classification_payload(
    frame: pd.DataFrame, *, target: str, model_name: str, random_state: int
) -> dict | None:
    y_train = normalize_target(frame[target])
    if y_train.nunique() < 2:
        return None
    raw = select_core_features(build_raw_feature_frame(frame))
    medians = raw.median(numeric_only=True)
    x_train = raw.fillna(medians).fillna(0)
    threshold = 0.5
    if str(model_name).endswith("_calibrated_sigmoid"):
        base_name = str(model_name).removesuffix("_calibrated_sigmoid")
        calibrated = fit_time_ordered_calibrator(
            name=base_name,
            x_train=x_train,
            y_train=y_train,
            random_state=random_state,
            target=target,
        )
        if calibrated is None:
            return None
        model, threshold = calibrated
    else:
        model = build_classification_model(
            str(model_name), y_train=y_train, random_state=random_state
        )
        if model is None:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train, y_train)
    return {
        "target_type": "classification",
        "model_name": model_name,
        "model": model,
        "feature_columns": list(x_train.columns),
        "numeric_medians": medians.to_dict(),
        "decision_threshold": threshold,
        "training_rows": len(frame),
    }


def train_regression_payload(
    frame: pd.DataFrame, *, target: str, model_name: str, random_state: int
) -> dict | None:
    x_train, _ = build_feature_pair(frame, frame.tail(1))
    y_train = pd.to_numeric(frame[target], errors="coerce")
    model = build_regression_model(str(model_name), random_state=random_state)
    if model is None:
        return None
    low_model, high_model = build_quantile_models(random_state=random_state)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(x_train, y_train)
        low_model.fit(x_train, y_train)
        high_model.fit(x_train, y_train)
    return {
        "target_type": "regression",
        "model_name": model_name,
        "model": model,
        "interval_low_model": low_model,
        "interval_high_model": high_model,
        "feature_columns": list(x_train.columns),
        "numeric_medians": x_train.median(numeric_only=True).to_dict(),
        "training_rows": len(frame),
    }


def build_shadow_prediction_records(
    dataset: pd.DataFrame,
    *,
    candidate_bundle: dict,
    model_run_id: str,
    universe: str = "QQQ100",
    provider: str = "yfinance",
) -> list[dict]:
    if candidate_bundle.get("status") != "success":
        return []
    latest = (
        dataset.sort_values(["date", "ticker"])
        .groupby("ticker", as_index=False)
        .tail(1)
        .copy()
    )
    candidate_version = candidate_bundle["candidate_version"]
    records = []
    for _, row in latest.iterrows():
        predictions = predict_row(row.to_dict(), candidate_bundle["models"])
        data_as_of = str(row.get("date") or date.today().isoformat())[:10]
        record = {
            "model_run_id": model_run_id,
            "ticker": str(row["ticker"]).upper(),
            "prediction_date": data_as_of,
            "data_as_of": data_as_of,
            "universe": universe,
            "price_provider": provider,
            "model_version": candidate_version,
            "feature_version": candidate_bundle.get("feature_version") or FEATURE_VERSION,
            "prediction_role": "shadow",
            "prediction_status": "ready",
            "prediction_freshness": "fresh",
            "up_probability_5d": predictions.get("up_5d"),
            "up_probability_10d": predictions.get("up_10d"),
            "up_probability_20d": predictions.get("up_20d"),
            "large_drop_risk_20d": predictions.get("large_drop_20d"),
            "predicted_return_5d": predictions.get("forward_return_5d"),
            "predicted_return_10d": predictions.get("forward_return_10d"),
            "predicted_return_20d": predictions.get("forward_return_20d"),
            "predicted_max_drop_20d": predictions.get("max_drop_20d"),
            "model_quality": "medium",
            "evidence_quality": "medium",
            "signal_clarity": "unknown",
            "data_completeness": "high",
            "news_coverage": normalize_quality(row.get("news_missing"), inverse=True),
            "fundamental_coverage": "unknown",
            "prediction_payload": {
                "usage_policy": "shadow_only",
                "research_report_visible": False,
                "candidate_version": candidate_version,
                "predictions": predictions,
            },
            "feature_snapshot": sanitize_mapping(row.to_dict()),
        }
        records.append(record)
    return records


def predict_row(row: dict, models: dict) -> dict:
    frame = pd.DataFrame([row])
    raw = select_core_features(build_raw_feature_frame(frame))
    output = {}
    for target, payload in models.items():
        columns = payload["feature_columns"]
        features = raw.copy()
        for column in columns:
            if column not in features:
                features[column] = 0
        features = features[columns]
        medians = pd.Series(payload.get("numeric_medians") or {})
        features = features.fillna(medians).fillna(0)
        if payload["target_type"] == "classification":
            output[target] = float(payload["model"].predict_proba(features)[:, 1][0])
        else:
            output[target] = float(payload["model"].predict(features)[0])
            low = float(payload["interval_low_model"].predict(features)[0])
            high = float(payload["interval_high_model"].predict(features)[0])
            output[f"{target}_range"] = {"low": min(low, high), "high": max(low, high)}
    return output


def sanitize_mapping(row: dict) -> dict:
    output = {}
    for key, value in row.items():
        if key == "_date":
            continue
        if isinstance(value, (list, tuple, dict, set)):
            output[key] = str(value)
        elif pd.isna(value):
            output[key] = None
        elif hasattr(value, "item"):
            output[key] = value.item()
        elif isinstance(value, (str, int, float, bool)):
            output[key] = value
        else:
            output[key] = str(value)
    return output


def normalize_quality(value, *, inverse: bool = False) -> str:
    if inverse:
        return "none" if bool(value) else "high"
    return "unknown"
