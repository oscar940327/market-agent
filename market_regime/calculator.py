from datetime import UTC, datetime

import pandas as pd


REGIME_RULE_VERSION = "v1"
THREE_MONTH_TRADING_DAYS = 63


def build_market_regime_records(
    *,
    benchmark: str,
    price_data: pd.DataFrame,
    rule_version: str = REGIME_RULE_VERSION,
) -> list[dict]:
    data = normalize_price_data(price_data)
    if data.empty:
        return []

    data["MA200"] = data["Close"].rolling(window=200).mean()
    data["THREE_MONTH_RETURN"] = (
        data["Close"] / data["Close"].shift(THREE_MONTH_TRADING_DAYS) - 1
    )
    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    records = []
    previous_regime = None
    data_as_of = data.index.max().date().isoformat()

    for index, row in data.iterrows():
        regime = classify_market_regime(
            close=safe_float(row["Close"]),
            ma200=safe_float(row["MA200"]),
            three_month_return=safe_float(row["THREE_MONTH_RETURN"]),
        )
        regime_changed = (
            previous_regime is not None
            and regime != "unknown"
            and previous_regime != "unknown"
            and regime != previous_regime
        )
        records.append(
            {
                "date": index.date().isoformat(),
                "benchmark": benchmark.upper(),
                "regime": regime,
                "close": safe_float(row["Close"]),
                "ma200": safe_float(row["MA200"]),
                "three_month_return": safe_float(row["THREE_MONTH_RETURN"]),
                "regime_changed": regime_changed,
                "previous_regime": previous_regime,
                "rule_version": rule_version,
                "data_as_of": data_as_of,
                "checked_at": checked_at,
            }
        )
        previous_regime = regime

    return records


def classify_market_regime(
    *,
    close: float | None,
    ma200: float | None,
    three_month_return: float | None,
) -> str:
    if close is None or ma200 is None or three_month_return is None:
        return "unknown"

    if close > ma200 and three_month_return > 0:
        return "bull"

    if close < ma200 and three_month_return < 0:
        return "bear"

    return "sideways"


def normalize_price_data(price_data: pd.DataFrame) -> pd.DataFrame:
    normalized = price_data.copy()

    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.set_index("date")

    column_map = {
        "close": "Close",
    }
    normalized = normalized.rename(columns=column_map)
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()

    if "Close" not in normalized.columns:
        return pd.DataFrame()

    return normalized


def safe_float(value) -> float | None:
    if pd.isna(value):
        return None

    return float(value)
