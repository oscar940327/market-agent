from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

from ml_versions import (
    DAILY_PREDICTION_VERSION,
    DATASET_VERSION,
    FEATURE_VERSION,
    MARKET_SNAPSHOT_VERSION,
    build_versioning_payload,
)


DEFAULT_UNIVERSE = "QQQ100"
DEFAULT_PROVIDER = "yfinance"
DEFAULT_MODEL_TYPE = "hybrid"
DEFAULT_RUN_TYPE = "daily_prediction"
DEFAULT_MODEL_VERSION = DAILY_PREDICTION_VERSION
DEFAULT_FEATURE_VERSION = FEATURE_VERSION


QUALITY_VALUES = {
    "high",
    "medium",
    "low_to_medium",
    "low",
    "none",
    "not_used",
    "not_applicable",
    "skipped",
    "unknown",
}


def build_ml_model_run_row(
    *,
    data_as_of: str | date,
    model_version: str = DEFAULT_MODEL_VERSION,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    dataset_version: str = DATASET_VERSION,
    universe: str = DEFAULT_UNIVERSE,
    provider: str = DEFAULT_PROVIDER,
    pipeline_run_id: str | None = None,
    started_at: datetime | None = None,
    status: str = "completed",
    metrics: dict | None = None,
    config: dict | None = None,
) -> dict:
    now = datetime.now(UTC)
    started = started_at or now
    versioning = build_versioning_payload()
    merged_config = {
        "versioning": versioning,
        **(config or {}),
    }
    return sanitize_json_value(
        {
            "run_name": f"{DEFAULT_RUN_TYPE}_{normalize_date(data_as_of)}",
            "run_type": DEFAULT_RUN_TYPE,
            "model_type": DEFAULT_MODEL_TYPE,
            "model_version": model_version,
            "feature_version": feature_version,
            "dataset_version": dataset_version,
            "universe": universe,
            "provider": provider,
            "data_as_of": normalize_date(data_as_of),
            "pipeline_run_id": pipeline_run_id,
            "metrics": metrics or {},
            "config": merged_config,
            "status": status,
            "started_at": started.isoformat(),
            "completed_at": now.isoformat(),
        }
    )


def build_prediction_record(
    *,
    ticker: str,
    model_run_id: str,
    ml_research: dict,
    feature_row: dict,
    ticker_metadata: dict | None = None,
    data_freshness: dict | None = None,
    universe: str = DEFAULT_UNIVERSE,
    price_provider: str = DEFAULT_PROVIDER,
) -> dict:
    ticker_metadata = ticker_metadata or {}
    data_freshness = data_freshness or {}
    data_as_of = normalize_date(
        feature_row.get("data_as_of") or feature_row.get("date") or date.today()
    )
    model_version = ml_research.get("model_version") or DEFAULT_MODEL_VERSION
    feature_version = (
        ml_research.get("feature_version")
        or feature_row.get("feature_version")
        or DEFAULT_FEATURE_VERSION
    )
    targets = ml_research.get("targets", {})
    return_reference = ml_research.get("return_reference", {})
    return_model = ml_research.get("return_model", {})
    return_targets = return_model.get("targets", {})
    states = build_snapshot_states(
        feature_row=feature_row,
        ml_research=ml_research,
        ticker_metadata=ticker_metadata,
        data_freshness=data_freshness,
    )
    versioning = build_versioning_payload()

    record = {
        "model_run_id": model_run_id,
        "ticker": ticker.upper(),
        "prediction_date": data_as_of,
        "data_as_of": data_as_of,
        "universe": universe,
        "price_provider": price_provider,
        "model_version": model_version,
        "feature_version": feature_version,
        "prediction_role": "production",
        "prediction_status": "ready" if ml_research.get("status") == "success" else "unavailable",
        "prediction_freshness": normalize_freshness(data_freshness.get("overall")),
        "up_probability_5d": target_probability(targets, "up_5d"),
        "up_probability_10d": target_probability(targets, "up_10d"),
        "up_probability_20d": target_probability(targets, "up_20d"),
        "large_drop_risk_20d": target_probability(targets, "large_drop_20d"),
        "historical_sample_size": return_reference.get("sample_size"),
        "historical_evidence_quality": normalize_quality(
            return_reference.get("evidence_quality")
        ),
        "historical_avg_return_5d": return_reference.get("historical_average_return_5d"),
        "historical_avg_return_10d": return_reference.get("historical_average_return_10d"),
        "historical_avg_return_20d": return_reference.get("historical_average_return_20d"),
        "historical_return_5d_p25": range_value(return_reference, "expected_return_range_5d", "low"),
        "historical_return_5d_p75": range_value(return_reference, "expected_return_range_5d", "high"),
        "historical_return_10d_p25": range_value(return_reference, "expected_return_range_10d", "low"),
        "historical_return_10d_p75": range_value(return_reference, "expected_return_range_10d", "high"),
        "historical_return_20d_p25": range_value(return_reference, "expected_return_range_20d", "low"),
        "historical_return_20d_p75": range_value(return_reference, "expected_return_range_20d", "high"),
        "historical_max_drop_20d_p25": range_value(return_reference, "max_drop_range_20d", "low"),
        "historical_max_drop_20d_p75": range_value(return_reference, "max_drop_range_20d", "high"),
        "predicted_return_5d": return_target_value(return_targets, "forward_return_5d"),
        "predicted_return_10d": return_target_value(return_targets, "forward_return_10d"),
        "predicted_return_20d": return_target_value(return_targets, "forward_return_20d"),
        "predicted_max_drop_20d": return_target_value(return_targets, "max_drop_20d"),
        "predicted_return_5d_p25": return_target_range(return_targets, "forward_return_5d", "low"),
        "predicted_return_5d_p75": return_target_range(return_targets, "forward_return_5d", "high"),
        "predicted_return_10d_p25": return_target_range(return_targets, "forward_return_10d", "low"),
        "predicted_return_10d_p75": return_target_range(return_targets, "forward_return_10d", "high"),
        "predicted_return_20d_p25": return_target_range(return_targets, "forward_return_20d", "low"),
        "predicted_return_20d_p75": return_target_range(return_targets, "forward_return_20d", "high"),
        "predicted_max_drop_20d_p25": return_target_range(return_targets, "max_drop_20d", "low"),
        "predicted_max_drop_20d_p75": return_target_range(return_targets, "max_drop_20d", "high"),
        "model_quality": normalize_quality(overall_model_quality(targets, return_model)),
        "evidence_quality": normalize_quality(overall_evidence_quality(ml_research)),
        "signal_clarity": normalize_quality(states["signal_clarity"]),
        "data_completeness": normalize_quality(states["data_completeness"]),
        "news_coverage": normalize_quality(states["news_coverage"]),
        "fundamental_coverage": normalize_quality(states["fundamental_coverage"]),
        "prediction_payload": {
            "versioning": versioning,
            "ml_research": ml_research,
            "market_snapshot": states,
            "ticker_metadata": ticker_metadata,
            "data_freshness": data_freshness,
        },
        "feature_snapshot": build_feature_snapshot(
            feature_row=feature_row,
            ticker_metadata=ticker_metadata,
            states=states,
        ),
    }
    return sanitize_json_value(record)


def build_failed_prediction_record(
    *,
    ticker: str,
    model_run_id: str,
    error_message: str,
    data_as_of: str | date | None = None,
    ticker_metadata: dict | None = None,
    universe: str = DEFAULT_UNIVERSE,
    price_provider: str = DEFAULT_PROVIDER,
    model_version: str = DEFAULT_MODEL_VERSION,
    feature_version: str = DEFAULT_FEATURE_VERSION,
) -> dict:
    normalized_date = normalize_date(data_as_of or date.today())
    metadata = ticker_metadata or {}
    return sanitize_json_value(
        {
            "model_run_id": model_run_id,
            "ticker": ticker.upper(),
            "prediction_date": normalized_date,
            "data_as_of": normalized_date,
            "universe": universe,
            "price_provider": price_provider,
            "model_version": model_version,
            "feature_version": feature_version,
            "prediction_role": "production",
            "prediction_status": "failed",
            "prediction_freshness": "unknown",
            "model_quality": "unknown",
            "evidence_quality": "unknown",
            "signal_clarity": "unknown",
            "data_completeness": "low",
            "news_coverage": "unknown",
            "fundamental_coverage": "unknown",
            "prediction_payload": {
                "status": "failed",
                "error": error_message,
                "versioning": build_versioning_payload(),
                "market_snapshot": {
                    "technical_state": "unknown",
                    "valuation_state": "unknown",
                    "news_state": "unknown",
                    "ml_state": "unavailable",
                    "risk_state": "unknown",
                    "data_freshness": "unknown",
                    "candidate_reason": "Prediction failed after retry.",
                    "observation_reason": "Prediction failed after retry.",
                },
                "ticker_metadata": metadata,
            },
            "feature_snapshot": {
                "ticker": ticker.upper(),
                "industry": metadata.get("industry"),
                "themes": metadata.get("themes") or [],
                "market_snapshot_version": MARKET_SNAPSHOT_VERSION,
            },
        }
    )


def build_snapshot_states(
    *,
    feature_row: dict,
    ml_research: dict,
    ticker_metadata: dict | None = None,
    data_freshness: dict | None = None,
) -> dict:
    ticker_metadata = ticker_metadata or {}
    targets = ml_research.get("targets", {})
    up_20d = target_probability(targets, "up_20d")
    large_drop = target_probability(targets, "large_drop_20d")
    news_count = safe_number(feature_row.get("news_count_30d"))
    news_sentiment = safe_number(feature_row.get("news_sentiment_score_30d"))
    risk_events = safe_number(feature_row.get("risk_event_count_30d"))

    technical_state = classify_technical_state(feature_row)
    news_state = classify_news_state(news_count, news_sentiment, risk_events)
    ml_state = classify_ml_state(up_20d)
    risk_state = classify_risk_state(large_drop, risk_events)
    freshness = normalize_freshness((data_freshness or {}).get("overall"))
    signal_clarity = classify_signal_clarity(feature_row, up_20d)
    data_completeness = classify_data_completeness(feature_row, freshness)
    news_coverage = classify_news_coverage(news_count)
    fundamental_coverage = "unknown"

    return {
        "ticker": str(feature_row.get("ticker", "")).upper(),
        "industry": ticker_metadata.get("industry"),
        "themes": ticker_metadata.get("themes") or [],
        "market_regime": feature_row.get("market_regime") or "unknown",
        "technical_state": technical_state,
        "valuation_state": "unknown",
        "news_state": news_state,
        "ml_state": ml_state,
        "risk_state": risk_state,
        "data_freshness": freshness,
        "signal_clarity": signal_clarity,
        "data_completeness": data_completeness,
        "news_coverage": news_coverage,
        "fundamental_coverage": fundamental_coverage,
        "candidate_reason": build_candidate_reason(
            technical_state=technical_state,
            news_state=news_state,
            ml_state=ml_state,
            risk_state=risk_state,
        ),
        "observation_reason": build_observation_reason(
            technical_state=technical_state,
            news_state=news_state,
            ml_state=ml_state,
            risk_state=risk_state,
        ),
    }


def build_feature_snapshot(
    *,
    feature_row: dict,
    ticker_metadata: dict,
    states: dict,
) -> dict:
    fields = [
        "ticker",
        "date",
        "data_as_of",
        "feature_version",
        "price_vs_ma5",
        "price_vs_ma10",
        "price_vs_ma20",
        "price_vs_ma50",
        "price_vs_ma200",
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
        "news_count_30d",
        "news_sentiment_score_30d",
        "high_importance_news_count_30d",
        "risk_event_count_30d",
        "earnings_guidance_count_30d",
        "product_demand_count_30d",
        "news_missing",
    ]
    snapshot = {field: feature_row.get(field) for field in fields}
    snapshot.update(
        {
            "industry": ticker_metadata.get("industry"),
            "themes": ticker_metadata.get("themes") or [],
            "market_snapshot": states,
        }
    )
    return sanitize_json_value(snapshot)


def select_ticker_metadata(rows: list[dict], tickers: list[str] | None = None) -> dict[str, dict]:
    selected = {row["ticker"].upper(): row for row in rows if row.get("ticker")}
    if tickers is None:
        return selected
    return {ticker.upper(): selected.get(ticker.upper(), {"ticker": ticker.upper()}) for ticker in tickers}


def classify_technical_state(feature_row: dict) -> str:
    if bool(feature_row.get("is_breakout")):
        return "breakout"
    if bool(feature_row.get("is_pullback")):
        return "pullback"
    if bool(feature_row.get("is_volume_surge")):
        return "volume_surge"

    price_vs_ma20 = safe_number(feature_row.get("price_vs_ma20"))
    macd_histogram = safe_number(feature_row.get("macd_histogram"))
    if price_vs_ma20 is None or macd_histogram is None:
        return "unknown"
    if price_vs_ma20 > 0 and macd_histogram > 0:
        return "bullish"
    if price_vs_ma20 < 0 and macd_histogram < 0:
        return "bearish"
    return "neutral"


def classify_news_state(
    news_count: float | None,
    news_sentiment: float | None,
    risk_events: float | None,
) -> str:
    if news_count is None or news_count <= 0:
        return "no_recent_news"
    if risk_events and risk_events > 0:
        return "risk_event"
    if news_sentiment is None:
        return "unknown"
    if news_sentiment >= 0.25:
        return "positive"
    if news_sentiment <= -0.25:
        return "negative"
    return "neutral"


def classify_ml_state(up_20d_probability: float | None) -> str:
    if up_20d_probability is None:
        return "unknown"
    if up_20d_probability >= 0.60:
        return "bullish"
    if up_20d_probability >= 0.53:
        return "slightly_bullish"
    if up_20d_probability <= 0.40:
        return "bearish"
    if up_20d_probability <= 0.47:
        return "slightly_bearish"
    return "unclear"


def classify_risk_state(
    large_drop_probability: float | None,
    risk_events: float | None,
) -> str:
    if risk_events and risk_events > 0:
        return "elevated"
    if large_drop_probability is None:
        return "unknown"
    if large_drop_probability >= 0.45:
        return "high"
    if large_drop_probability >= 0.30:
        return "medium"
    if large_drop_probability >= 0.18:
        return "low_to_medium"
    return "low"


def classify_signal_clarity(feature_row: dict, up_20d_probability: float | None) -> str:
    triggered = [
        bool(feature_row.get("is_breakout")),
        bool(feature_row.get("is_volume_surge")),
        bool(feature_row.get("is_pullback")),
    ]
    if any(triggered):
        return "medium"
    if up_20d_probability is None:
        return "unknown"
    if up_20d_probability >= 0.60 or up_20d_probability <= 0.40:
        return "medium"
    if up_20d_probability >= 0.53 or up_20d_probability <= 0.47:
        return "low_to_medium"
    return "low"


def classify_data_completeness(feature_row: dict, freshness: str) -> str:
    required_fields = [
        "price_vs_ma20",
        "rsi_14",
        "macd",
        "macd_histogram",
        "market_regime",
    ]
    present_count = sum(feature_row.get(field) is not None for field in required_fields)
    if freshness in {"stale", "missing"}:
        return "low"
    if present_count == len(required_fields):
        return "high"
    if present_count >= 3:
        return "medium"
    if present_count >= 1:
        return "low_to_medium"
    return "low"


def classify_news_coverage(news_count: float | None) -> str:
    if news_count is None or news_count <= 0:
        return "none"
    if news_count >= 10:
        return "high"
    if news_count >= 3:
        return "medium"
    return "low_to_medium"


def build_candidate_reason(
    *,
    technical_state: str,
    news_state: str,
    ml_state: str,
    risk_state: str,
) -> str:
    reasons = []
    if technical_state in {"breakout", "bullish", "pullback"}:
        reasons.append(f"technical_state={technical_state}")
    if news_state in {"positive", "risk_event"}:
        reasons.append(f"news_state={news_state}")
    if ml_state in {"bullish", "slightly_bullish"}:
        reasons.append(f"ml_state={ml_state}")
    if risk_state in {"high", "elevated"}:
        reasons.append(f"risk_state={risk_state}")
    if not reasons:
        return "No clear candidate reason yet."
    return "; ".join(reasons)


def build_observation_reason(
    *,
    technical_state: str,
    news_state: str,
    ml_state: str,
    risk_state: str,
) -> str:
    return (
        f"technical={technical_state}; news={news_state}; "
        f"ml={ml_state}; risk={risk_state}"
    )


def target_probability(targets: dict, target: str) -> float | None:
    return sanitize_json_value(targets.get(target, {}).get("probability"))


def range_value(payload: dict, key: str, side: str) -> float | None:
    value = payload.get(key)
    if not isinstance(value, dict):
        return None
    return sanitize_json_value(value.get(side))


def return_target_value(targets: dict, target: str) -> float | None:
    return sanitize_json_value(targets.get(target, {}).get("predicted_value"))


def return_target_range(targets: dict, target: str, side: str) -> float | None:
    value = targets.get(target, {}).get("predicted_range")
    if not isinstance(value, dict):
        return None
    return sanitize_json_value(value.get(side))


def overall_model_quality(targets: dict, return_model: dict) -> str:
    qualities = [
        target.get("signal_quality")
        for target in targets.values()
        if isinstance(target, dict) and target.get("signal_quality")
    ]
    return_targets = return_model.get("targets", {}) if isinstance(return_model, dict) else {}
    qualities.extend(
        target.get("model_quality")
        for target in return_targets.values()
        if isinstance(target, dict) and target.get("model_quality")
    )
    return lowest_quality(qualities)


def overall_evidence_quality(ml_research: dict) -> str:
    reference = ml_research.get("return_reference", {})
    quality = reference.get("evidence_quality")
    if quality:
        return normalize_quality(quality)
    return overall_model_quality(ml_research.get("targets", {}), ml_research.get("return_model", {}))


def lowest_quality(qualities: list[str | None]) -> str:
    rank = {
        "high": 5,
        "medium": 4,
        "low_to_medium": 3,
        "low": 2,
        "none": 1,
        "unknown": 0,
    }
    normalized = [normalize_quality(quality) for quality in qualities if quality]
    if not normalized:
        return "unknown"
    return min(normalized, key=lambda quality: rank.get(quality, 0))


def normalize_quality(value: Any) -> str:
    if not value:
        return "unknown"
    normalized = str(value).replace("-", "_").lower()
    return normalized if normalized in QUALITY_VALUES else "unknown"


def normalize_freshness(value: Any) -> str:
    if value in {"fresh", "warning", "stale", "missing", "unknown"}:
        return str(value)
    return "unknown"


def normalize_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def safe_number(value: Any) -> float | None:
    value = sanitize_json_value(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return sanitize_json_value(value.item())
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json_value(item) for item in value]
    return value
