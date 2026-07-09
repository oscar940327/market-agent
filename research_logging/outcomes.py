from datetime import UTC, datetime

import pandas as pd


RESEARCH_OUTCOME_UPDATE_FIELDS = (
    "research_log_id",
    "ticker",
    "query_date",
    "intent",
    "theme",
    "conclusion",
    "exit_signal",
    "horizon_trading_days",
    "target_date",
    "actual_date",
    "price_at_query",
    "price_at_horizon",
    "return_pct",
    "max_drawdown_pct",
    "max_runup_pct",
    "entry_touched",
    "exit_touched",
    "stop_loss_touched",
    "outcome_status",
    "price_provider",
    "price_plan",
    "tracking_notes",
    "used_for_calibration",
    "calibration_notes",
    "computed_at",
)


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
    passthrough = build_passthrough_fields(outcome)

    if price_data.empty:
        return build_missing_price_update(
            research_log_id=research_log_id,
            horizon=horizon,
            ticker=ticker,
            query_date=query_date,
            price_provider=price_provider,
            passthrough=passthrough,
        )

    future_prices = price_data[price_data.index >= query_date]

    if len(future_prices) <= horizon:
        return normalize_research_outcome_update(
            {
                "research_log_id": research_log_id,
                "ticker": ticker,
                "query_date": query_date.date().isoformat(),
                "horizon_trading_days": horizon,
                "price_at_query": outcome.get("price_at_query"),
                "outcome_status": "pending",
                "price_provider": price_provider,
                **passthrough,
                "used_for_calibration": False,
                "target_date": None,
                "actual_date": None,
                "computed_at": None,
            }
        )

    query_row = future_prices.iloc[0]
    horizon_window = future_prices.iloc[: horizon + 1]
    horizon_row = horizon_window.iloc[-1]
    price_at_query = float(outcome.get("price_at_query") or query_row["close"])
    price_at_horizon = float(horizon_row["close"])
    returns = (horizon_window["close"] - price_at_query) / price_at_query
    touch_result = evaluate_price_plan_touches(
        price_plan=outcome.get("price_plan") or {},
        price_window=horizon_window,
    )

    return normalize_research_outcome_update(
        {
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
            **touch_result,
            "outcome_status": "computed",
            "price_provider": price_provider,
            **passthrough,
            "used_for_calibration": False,
            "calibration_notes": None,
            "computed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
    )


def build_missing_price_update(
    *,
    research_log_id: str,
    horizon: int,
    ticker: str,
    query_date: pd.Timestamp,
    price_provider: str,
    passthrough: dict | None = None,
) -> dict:
    return normalize_research_outcome_update(
        {
            "research_log_id": research_log_id,
            "ticker": ticker,
            "query_date": query_date.date().isoformat(),
            "horizon_trading_days": horizon,
            "outcome_status": "missing_price",
            "price_provider": price_provider,
            **(passthrough or {}),
            "used_for_calibration": False,
            "computed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
    )


def normalize_research_outcome_update(row: dict) -> dict:
    return {field: row.get(field) for field in RESEARCH_OUTCOME_UPDATE_FIELDS}


def build_passthrough_fields(outcome: dict) -> dict:
    return {
        "intent": outcome.get("intent"),
        "theme": outcome.get("theme"),
        "conclusion": outcome.get("conclusion"),
        "exit_signal": outcome.get("exit_signal"),
        "price_plan": outcome.get("price_plan") or {},
        "tracking_notes": outcome.get("tracking_notes"),
    }


def evaluate_price_plan_touches(*, price_plan: dict, price_window: pd.DataFrame) -> dict:
    entry_range = extract_range(price_plan, "entry")
    exit_range = extract_range(price_plan, "exit")
    stop_loss = extract_stop_loss(price_plan)

    return {
        "entry_touched": range_touched(price_window, entry_range),
        "exit_touched": range_touched(price_window, exit_range),
        "stop_loss_touched": stop_loss_touched(price_window, stop_loss),
    }


def extract_range(price_plan: dict, prefix: str) -> tuple[float, float] | None:
    candidates = [
        price_plan.get(f"{prefix}_range"),
        price_plan.get(f"suggested_{prefix}_range"),
        price_plan.get(f"{prefix}_price_range"),
    ]
    for candidate in candidates:
        normalized = normalize_range(candidate)
        if normalized:
            return normalized

    low = safe_float(
        price_plan.get(f"{prefix}_low")
        or price_plan.get(f"suggested_{prefix}_low")
        or price_plan.get(f"{prefix}_range_low")
    )
    high = safe_float(
        price_plan.get(f"{prefix}_high")
        or price_plan.get(f"suggested_{prefix}_high")
        or price_plan.get(f"{prefix}_range_high")
    )
    if low is None or high is None:
        return None
    return (min(low, high), max(low, high))


def normalize_range(value) -> tuple[float, float] | None:
    if isinstance(value, dict):
        low = safe_float(value.get("low") or value.get("min"))
        high = safe_float(value.get("high") or value.get("max"))
        if low is not None and high is not None:
            return (min(low, high), max(low, high))

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        low = safe_float(value[0])
        high = safe_float(value[1])
        if low is not None and high is not None:
            return (min(low, high), max(low, high))

    return None


def extract_stop_loss(price_plan: dict) -> float | None:
    return safe_float(
        price_plan.get("stop_loss")
        or price_plan.get("stop_loss_price")
        or price_plan.get("stop_loss_below")
        or price_plan.get("suggested_stop_loss")
    )


def range_touched(
    price_window: pd.DataFrame,
    price_range: tuple[float, float] | None,
) -> bool | None:
    if not price_range:
        return None

    low, high = price_range
    window_low = price_window["low"] if "low" in price_window else price_window["close"]
    window_high = price_window["high"] if "high" in price_window else price_window["close"]
    return bool(((window_low <= high) & (window_high >= low)).any())


def stop_loss_touched(price_window: pd.DataFrame, stop_loss: float | None) -> bool | None:
    if stop_loss is None:
        return None

    window_low = price_window["low"] if "low" in price_window else price_window["close"]
    return bool((window_low <= stop_loss).any())


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
