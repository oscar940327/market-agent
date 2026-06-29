from datetime import UTC, datetime

import pandas as pd


def build_outcome_updates(
    *,
    pending_outcomes: list[dict],
    price_data: pd.DataFrame,
) -> list[dict]:
    normalized_prices = normalize_price_data(price_data)
    updates = []

    for outcome in pending_outcomes:
        updates.append(
            build_single_outcome_update(
                outcome=outcome,
                price_data=normalized_prices,
            )
        )

    return updates


def build_single_outcome_update(
    *,
    outcome: dict,
    price_data: pd.DataFrame,
) -> dict:
    query_date = pd.Timestamp(outcome["query_date"])
    horizon = int(outcome["horizon_trading_days"])
    ticker = outcome["ticker"]
    price_provider = outcome.get("price_provider", "yfinance")
    research_log_id = outcome["research_log_id"]

    if price_data.empty:
        return build_missing_price_update(
            research_log_id=research_log_id,
            horizon=horizon,
            ticker=ticker,
            query_date=query_date,
            price_provider=price_provider,
        )

    future_prices = price_data[price_data.index >= query_date]

    if len(future_prices) <= horizon:
        return {
            "research_log_id": research_log_id,
            "ticker": ticker,
            "query_date": query_date.date().isoformat(),
            "horizon_trading_days": horizon,
            "outcome_status": "pending",
            "price_provider": price_provider,
            "used_for_calibration": False,
            "target_date": None,
            "actual_date": None,
            "computed_at": None,
        }

    query_row = future_prices.iloc[0]
    horizon_window = future_prices.iloc[: horizon + 1]
    horizon_row = horizon_window.iloc[-1]
    price_at_query = float(outcome.get("price_at_query") or query_row["close"])
    price_at_horizon = float(horizon_row["close"])
    returns = (horizon_window["close"] - price_at_query) / price_at_query

    return {
        "research_log_id": research_log_id,
        "ticker": ticker,
        "query_date": query_date.date().isoformat(),
        "horizon_trading_days": horizon,
        "target_date": horizon_row.name.date().isoformat(),
        "actual_date": horizon_row.name.date().isoformat(),
        "price_at_query": price_at_query,
        "price_at_horizon": price_at_horizon,
        "return_pct": round(float((price_at_horizon - price_at_query) / price_at_query), 6),
        "max_drawdown_pct": round(float(returns.min()), 6),
        "max_runup_pct": round(float(returns.max()), 6),
        "outcome_status": "computed",
        "price_provider": price_provider,
        "used_for_calibration": False,
        "calibration_notes": None,
        "computed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def build_missing_price_update(
    *,
    research_log_id: str,
    horizon: int,
    ticker: str,
    query_date: pd.Timestamp,
    price_provider: str,
) -> dict:
    return {
        "research_log_id": research_log_id,
        "ticker": ticker,
        "query_date": query_date.date().isoformat(),
        "horizon_trading_days": horizon,
        "outcome_status": "missing_price",
        "price_provider": price_provider,
        "used_for_calibration": False,
        "computed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def normalize_price_data(price_data: pd.DataFrame) -> pd.DataFrame:
    normalized = price_data.copy()

    if normalized.empty:
        return normalized

    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.set_index("date")

    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()

    return normalized
