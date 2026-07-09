from __future__ import annotations

from ml_model_improvement.downside_overlay import apply_downside_risk_overlay


USABLE_PREDICTION_STATUSES = {"ready"}
USABLE_FRESHNESS_STATUSES = {"fresh", "warning"}


def is_saved_prediction_usable(prediction: dict | None) -> bool:
    if not prediction:
        return False
    return (
        prediction.get("prediction_status") in USABLE_PREDICTION_STATUSES
        and prediction.get("prediction_freshness") in USABLE_FRESHNESS_STATUSES
    )


def convert_saved_prediction_to_ml_research(prediction: dict) -> dict:
    payload = prediction.get("prediction_payload") or {}
    ml_research = payload.get("ml_research")
    if isinstance(ml_research, dict) and ml_research:
        converted = dict(ml_research)
    else:
        converted = rebuild_ml_research_from_columns(prediction)

    converted["source"] = build_ml_source(
        source_type="saved_daily_prediction",
        prediction=prediction,
    )
    return apply_downside_risk_overlay(
        converted,
        prediction.get("feature_snapshot") or {},
    )


def build_runtime_fallback_source(
    *,
    reason: str,
    saved_prediction: dict | None = None,
) -> dict:
    source = {
        "type": "runtime_fallback",
        "reason": reason,
        "saved_prediction_available": bool(saved_prediction),
    }
    if saved_prediction:
        source.update(
            {
                "saved_prediction_status": saved_prediction.get("prediction_status"),
                "saved_prediction_freshness": saved_prediction.get(
                    "prediction_freshness"
                ),
                "saved_prediction_data_as_of": saved_prediction.get("data_as_of"),
                "saved_prediction_model_version": saved_prediction.get(
                    "model_version"
                ),
            }
        )
    return source


def build_unavailable_source(*, reason: str, saved_prediction: dict | None = None) -> dict:
    source = build_runtime_fallback_source(
        reason=reason,
        saved_prediction=saved_prediction,
    )
    source["type"] = "unavailable"
    return source


def build_ml_source(*, source_type: str, prediction: dict) -> dict:
    return {
        "type": source_type,
        "data_as_of": prediction.get("data_as_of"),
        "prediction_date": prediction.get("prediction_date"),
        "prediction_freshness": prediction.get("prediction_freshness"),
        "prediction_status": prediction.get("prediction_status"),
        "model_version": prediction.get("model_version"),
        "feature_version": prediction.get("feature_version"),
        "model_run_id": prediction.get("model_run_id"),
    }


def rebuild_ml_research_from_columns(prediction: dict) -> dict:
    return {
        "status": "success",
        "usage_policy": "reference_only",
        "model_version": prediction.get("model_version"),
        "feature_version": prediction.get("feature_version"),
        "targets": {
            "up_5d": build_target(
                probability=prediction.get("up_probability_5d"),
                model_target="up_5d",
            ),
            "up_10d": build_target(
                probability=prediction.get("up_probability_10d"),
                model_target="up_10d",
            ),
            "up_20d": build_target(
                probability=prediction.get("up_probability_20d"),
                model_target="up_20d",
            ),
            "large_drop_20d": build_target(
                probability=prediction.get("large_drop_risk_20d"),
                model_target="large_drop_20d",
            ),
        },
        "return_reference": {
            "method": "saved_daily_prediction_columns",
            "sample_size": prediction.get("historical_sample_size"),
            "evidence_quality": prediction.get("historical_evidence_quality"),
            "historical_average_return_5d": prediction.get("historical_avg_return_5d"),
            "historical_average_return_10d": prediction.get("historical_avg_return_10d"),
            "historical_average_return_20d": prediction.get("historical_avg_return_20d"),
            "expected_return_range_5d": build_range(
                prediction.get("historical_return_5d_p25"),
                prediction.get("historical_return_5d_p75"),
            ),
            "expected_return_range_10d": build_range(
                prediction.get("historical_return_10d_p25"),
                prediction.get("historical_return_10d_p75"),
            ),
            "expected_return_range_20d": build_range(
                prediction.get("historical_return_20d_p25"),
                prediction.get("historical_return_20d_p75"),
            ),
            "max_drop_range_20d": build_range(
                prediction.get("historical_max_drop_20d_p25"),
                prediction.get("historical_max_drop_20d_p75"),
            ),
        },
        "return_model": {
            "status": "success",
            "usage_policy": "experimental_reference_only",
            "targets": {
                "forward_return_5d": build_return_target(
                    value=prediction.get("predicted_return_5d"),
                    low=prediction.get("predicted_return_5d_p25"),
                    high=prediction.get("predicted_return_5d_p75"),
                    quality=prediction.get("model_quality"),
                ),
                "forward_return_10d": build_return_target(
                    value=prediction.get("predicted_return_10d"),
                    low=prediction.get("predicted_return_10d_p25"),
                    high=prediction.get("predicted_return_10d_p75"),
                    quality=prediction.get("model_quality"),
                ),
                "forward_return_20d": build_return_target(
                    value=prediction.get("predicted_return_20d"),
                    low=prediction.get("predicted_return_20d_p25"),
                    high=prediction.get("predicted_return_20d_p75"),
                    quality=prediction.get("model_quality"),
                ),
                "max_drop_20d": build_return_target(
                    value=prediction.get("predicted_max_drop_20d"),
                    low=prediction.get("predicted_max_drop_20d_p25"),
                    high=prediction.get("predicted_max_drop_20d_p75"),
                    quality=prediction.get("model_quality"),
                ),
            },
        },
        "summary": "ML reference loaded from saved daily prediction columns.",
    }


def build_target(*, probability, model_target: str) -> dict:
    if probability is None:
        return {
            "probability": None,
            "probability_percent": None,
            "signal_label": "unknown",
            "signal_quality": "unknown",
            "model_target": model_target,
        }
    probability = float(probability)
    return {
        "probability": probability,
        "probability_percent": round(probability * 100, 1),
        "signal_label": classify_signal_label(model_target, probability),
        "signal_quality": "unknown",
        "model_target": model_target,
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


def build_range(low, high) -> dict | None:
    if low is None and high is None:
        return None
    return {"low": low, "high": high, "method": "saved_daily_prediction"}


def build_return_target(*, value, low, high, quality) -> dict:
    return {
        "predicted_value": value,
        "predicted_percent": None if value is None else round(float(value) * 100, 1),
        "predicted_range": {
            "low": low,
            "high": high,
            "low_percent": None if low is None else round(float(low) * 100, 1),
            "high_percent": None if high is None else round(float(high) * 100, 1),
        },
        "model_quality": quality or "unknown",
    }
