from datetime import UTC, datetime

import pandas as pd


OUTCOME_HORIZONS = (5, 10, 20)
LARGE_DROP_THRESHOLD = -0.08
PROBABILITY_THRESHOLD = 0.5


def build_ml_prediction_outcome_updates(
    *,
    predictions: list[dict],
    price_rows_by_ticker: dict[tuple[str, str], list[dict]],
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
) -> list[dict]:
    updates = []
    normalized_prices = {
        key: normalize_price_data(pd.DataFrame(rows))
        for key, rows in price_rows_by_ticker.items()
    }

    for prediction in predictions:
        ticker = prediction["ticker"].upper()
        provider = prediction.get("price_provider") or "yfinance"
        price_data = normalized_prices.get((ticker, provider), pd.DataFrame())
        updates.extend(
            build_single_ml_prediction_outcomes(
                prediction=prediction,
                price_data=price_data,
                horizons=horizons,
            )
        )

    return updates


def build_single_ml_prediction_outcomes(
    *,
    prediction: dict,
    price_data: pd.DataFrame,
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
) -> list[dict]:
    return [
        build_horizon_outcome(
            prediction=prediction,
            price_data=normalize_price_data(price_data),
            horizon=horizon,
        )
        for horizon in horizons
    ]


def build_horizon_outcome(
    *,
    prediction: dict,
    price_data: pd.DataFrame,
    horizon: int,
) -> dict:
    prediction_date = pd.Timestamp(prediction["prediction_date"])
    ticker = prediction["ticker"].upper()
    provider = prediction.get("price_provider") or "yfinance"
    base_row = build_base_outcome_row(prediction=prediction, horizon=horizon)

    if price_data.empty:
        return {
            **base_row,
            "outcome_status": "missing_price",
            "computed_at": current_timestamp(),
        }

    if prediction_date not in price_data.index:
        return {
            **base_row,
            "outcome_status": "missing_price",
            "computed_at": current_timestamp(),
        }

    future_prices = price_data[price_data.index >= prediction_date]
    if len(future_prices) <= horizon:
        return {
            **base_row,
            "outcome_status": "pending",
            "computed_at": None,
        }

    prediction_price = safe_float(
        prediction.get("price_at_prediction")
        or prediction.get("feature_snapshot", {}).get("close")
        or future_prices.iloc[0]["close"]
    )
    if prediction_price is None or prediction_price <= 0:
        return {
            **base_row,
            "outcome_status": "missing_price",
            "computed_at": current_timestamp(),
        }

    horizon_window = future_prices.iloc[: horizon + 1]
    horizon_row = horizon_window.iloc[-1]
    horizon_price = safe_float(horizon_row["close"])
    if horizon_price is None:
        return {
            **base_row,
            "outcome_status": "missing_price",
            "computed_at": current_timestamp(),
        }

    returns = (horizon_window["close"].astype(float) - prediction_price) / prediction_price
    actual_return = float((horizon_price - prediction_price) / prediction_price)
    actual_up = actual_return > 0
    actual_max_drop = float(returns.min())
    actual_max_runup = float(returns.max())
    actual_large_drop = actual_max_drop <= LARGE_DROP_THRESHOLD
    predicted_up_probability = get_predicted_up_probability(prediction, horizon)
    predicted_return = get_predicted_return(prediction, horizon)
    predicted_large_drop_risk = (
        safe_float(prediction.get("large_drop_risk_20d")) if horizon == 20 else None
    )
    large_drop_threshold = get_probability_threshold(
        prediction,
        target="large_drop_20d",
    )

    return {
        **base_row,
        "target_date": horizon_row.name.date().isoformat(),
        "actual_date": horizon_row.name.date().isoformat(),
        "price_at_prediction": round(prediction_price, 6),
        "price_at_horizon": round(horizon_price, 6),
        "actual_return_pct": round(actual_return, 6),
        "actual_up": actual_up,
        "actual_max_drop_pct": round(actual_max_drop, 6),
        "actual_max_runup_pct": round(actual_max_runup, 6),
        "predicted_up_probability": predicted_up_probability,
        "predicted_return": predicted_return,
        "predicted_large_drop_risk": predicted_large_drop_risk,
        "up_prediction_correct": build_probability_correctness(
            probability=predicted_up_probability,
            actual=actual_up,
        ),
        "large_drop_prediction_correct": (
            build_probability_correctness(
                probability=predicted_large_drop_risk,
                actual=actual_large_drop,
                threshold=large_drop_threshold,
            )
            if horizon == 20
            else None
        ),
        "return_error": (
            round(actual_return - predicted_return, 6)
            if predicted_return is not None
            else None
        ),
        "outcome_status": "computed",
        "computed_at": current_timestamp(),
    }


def build_base_outcome_row(*, prediction: dict, horizon: int) -> dict:
    return {
        "ml_prediction_id": prediction["id"],
        "ticker": prediction["ticker"].upper(),
        "prediction_date": normalize_date(prediction["prediction_date"]),
        "horizon_trading_days": horizon,
        "target_date": None,
        "actual_date": None,
        "price_at_prediction": safe_float(prediction.get("price_at_prediction")),
        "price_at_horizon": None,
        "actual_return_pct": None,
        "actual_up": None,
        "actual_max_drop_pct": None,
        "actual_max_runup_pct": None,
        "predicted_up_probability": get_predicted_up_probability(prediction, horizon),
        "predicted_return": get_predicted_return(prediction, horizon),
        "predicted_large_drop_risk": (
            safe_float(prediction.get("large_drop_risk_20d")) if horizon == 20 else None
        ),
        "up_prediction_correct": None,
        "large_drop_prediction_correct": None,
        "return_error": None,
        "outcome_status": "pending",
        "price_provider": prediction.get("price_provider") or "yfinance",
        "computed_at": None,
    }


def normalize_price_data(price_data: pd.DataFrame | list[dict]) -> pd.DataFrame:
    normalized = pd.DataFrame(price_data) if isinstance(price_data, list) else price_data.copy()
    if normalized.empty:
        return normalized
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.set_index("date")
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()
    return normalized


def get_predicted_up_probability(prediction: dict, horizon: int) -> float | None:
    return safe_float(prediction.get(f"up_probability_{horizon}d"))


def get_predicted_return(prediction: dict, horizon: int) -> float | None:
    return safe_float(prediction.get(f"predicted_return_{horizon}d"))


def get_probability_threshold(prediction: dict, *, target: str) -> float:
    payload = prediction.get("prediction_payload") or {}
    thresholds = payload.get("decision_thresholds") or {}
    threshold = safe_float(thresholds.get(target))
    return threshold if threshold is not None else PROBABILITY_THRESHOLD


def build_probability_correctness(
    *,
    probability: float | None,
    actual: bool,
    threshold: float = PROBABILITY_THRESHOLD,
) -> bool | None:
    if probability is None:
        return None
    return (probability >= threshold) == actual


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_date(value) -> str:
    return str(value)[:10]


def current_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
