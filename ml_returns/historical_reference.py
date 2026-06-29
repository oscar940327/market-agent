import pandas as pd


HORIZONS = ["5d", "10d", "20d"]
MIN_SAMPLE_SIZE = 30


def build_historical_return_reference(
    *,
    feature_row: dict,
    dataset: pd.DataFrame,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> dict:
    normalized_dataset = dataset.copy()
    normalized_dataset["date"] = pd.to_datetime(normalized_dataset["date"])
    row_date = pd.to_datetime(feature_row["date"])
    history = normalized_dataset[normalized_dataset["date"] < row_date].copy()

    if history.empty:
        return empty_reference(reason="no_history_before_query_date")

    selected_rows, scope = select_historical_sample(
        feature_row=feature_row,
        history=history,
        min_sample_size=min_sample_size,
    )
    if selected_rows.empty:
        return empty_reference(reason="no_matching_historical_sample")

    reference = {
        "method": "historical_quantile_reference",
        "note": "Return ranges are historical references, not guaranteed outcomes.",
        "sample_size": int(len(selected_rows)),
        "similarity_scope": scope,
        "evidence_quality": classify_return_reference_quality(len(selected_rows), scope),
    }

    for horizon in HORIZONS:
        forward_column = f"forward_return_{horizon}"
        reference[f"historical_average_return_{horizon}"] = safe_mean(
            selected_rows[forward_column]
        )
        reference[f"expected_return_range_{horizon}"] = build_quantile_range(
            selected_rows[forward_column],
            method="historical_p25_p75",
        )
        upside_rows = selected_rows[selected_rows[forward_column] > 0]
        reference[f"upside_return_range_{horizon}"] = build_quantile_range(
            upside_rows[forward_column],
            method="historical_upside_p25_p75",
        )

    reference["max_drop_range_20d"] = build_quantile_range(
        selected_rows["max_drop_20d"],
        method="historical_max_drop_p25_p75",
    )
    return reference


def select_historical_sample(
    *,
    feature_row: dict,
    history: pd.DataFrame,
    min_sample_size: int,
) -> tuple[pd.DataFrame, str]:
    candidates = [
        (
            "same_ticker_same_regime_same_signal",
            same_ticker(history, feature_row)
            & same_regime(history, feature_row)
            & same_signal(history, feature_row),
        ),
        (
            "same_ticker_same_regime",
            same_ticker(history, feature_row) & same_regime(history, feature_row),
        ),
        ("same_ticker", same_ticker(history, feature_row)),
        (
            "same_regime_similar_technical_bucket",
            same_regime(history, feature_row)
            & same_technical_buckets(history, feature_row),
        ),
        ("full_historical_dataset", pd.Series(True, index=history.index)),
    ]

    fallback_rows = pd.DataFrame()
    fallback_scope = "none"
    for scope, mask in candidates:
        rows = history[mask].copy()
        if len(rows) >= min_sample_size:
            return rows, scope
        if len(rows) > len(fallback_rows):
            fallback_rows = rows
            fallback_scope = scope

    return fallback_rows, fallback_scope


def same_ticker(history: pd.DataFrame, feature_row: dict) -> pd.Series:
    return history["ticker"].astype(str).str.upper() == str(feature_row["ticker"]).upper()


def same_regime(history: pd.DataFrame, feature_row: dict) -> pd.Series:
    return history["market_regime"].astype(str) == str(
        feature_row.get("market_regime", "unknown")
    )


def same_signal(history: pd.DataFrame, feature_row: dict) -> pd.Series:
    return history.apply(signal_type, axis=1) == signal_type(feature_row)


def same_technical_buckets(history: pd.DataFrame, feature_row: dict) -> pd.Series:
    return (
        history["rsi_14"].map(rsi_bucket) == rsi_bucket(feature_row.get("rsi_14"))
    ) & (
        history["volatility_20d"].map(volatility_bucket)
        == volatility_bucket(feature_row.get("volatility_20d"))
    ) & (
        history["price_vs_ma20"].map(price_vs_ma20_bucket)
        == price_vs_ma20_bucket(feature_row.get("price_vs_ma20"))
    )


def signal_type(row) -> str:
    if bool_value(row.get("is_breakout")):
        return "breakout"
    if bool_value(row.get("is_volume_surge")):
        return "volume_surge"
    if bool_value(row.get("is_pullback")):
        return "pullback"
    return "none"


def rsi_bucket(value) -> str:
    value = safe_float(value)
    if value is None:
        return "unknown"
    if value < 40:
        return "weak"
    if value < 55:
        return "neutral"
    if value < 70:
        return "strong"
    return "overbought"


def volatility_bucket(value) -> str:
    value = safe_float(value)
    if value is None:
        return "unknown"
    if value < 0.02:
        return "low"
    if value < 0.04:
        return "medium"
    return "high"


def price_vs_ma20_bucket(value) -> str:
    value = safe_float(value)
    if value is None:
        return "unknown"
    if value < -0.05:
        return "below"
    if value <= 0.05:
        return "near"
    return "above"


def build_quantile_range(series: pd.Series, *, method: str) -> dict | None:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return {
        "low": float(cleaned.quantile(0.25)),
        "high": float(cleaned.quantile(0.75)),
        "method": method,
        "sample_size": int(len(cleaned)),
    }


def safe_mean(series: pd.Series) -> float | None:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.mean())


def classify_return_reference_quality(sample_size: int, scope: str) -> str:
    if sample_size <= 0:
        return "none"

    if sample_size >= 200 and scope != "full_historical_dataset":
        return "high"

    if sample_size >= 100:
        return "medium"

    if sample_size >= 30:
        return "low_to_medium"

    if sample_size >= 5:
        return "low"

    return "none"


def empty_reference(*, reason: str) -> dict:
    return {
        "method": "historical_quantile_reference",
        "note": "Return ranges are unavailable because there is not enough history.",
        "sample_size": 0,
        "similarity_scope": "none",
        "evidence_quality": "none",
        "reason": reason,
    }


def bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def safe_float(value) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
