from datetime import UTC, datetime

import pandas as pd

from skills.technical_analysis_skill import calculate_macd, calculate_rsi


FEATURE_VERSION = "v1"


def build_technical_feature_records(
    *,
    ticker: str,
    price_provider: str,
    price_data: pd.DataFrame,
    feature_version: str = FEATURE_VERSION,
) -> list[dict]:
    if price_data is None or price_data.empty:
        return []

    data = normalize_daily_price_frame(price_data)
    if data.empty:
        return []

    data["MA5"] = data["Close"].rolling(window=5).mean()
    data["MA10"] = data["Close"].rolling(window=10).mean()
    data["MA20"] = data["Close"].rolling(window=20).mean()
    data["MA50"] = data["Close"].rolling(window=50).mean()
    data["MA200"] = data["Close"].rolling(window=200).mean()
    data["RSI14"] = calculate_rsi(data["Close"], window=14)
    data["MACD"], data["MACD_SIGNAL"], data["MACD_HISTOGRAM"] = calculate_macd(
        data["Close"]
    )
    data["AVERAGE_VOLUME_20"] = data["Volume"].rolling(window=20).mean()
    data["AVERAGE_VOLUME_5"] = data["Volume"].rolling(window=5).mean()
    data["DRAWDOWN_FROM_20D_HIGH"] = data["Close"] / data["Close"].rolling(window=20).max() - 1
    data["DRAWDOWN_FROM_60D_HIGH"] = data["Close"] / data["Close"].rolling(window=60).max() - 1
    data["MA20_SLOPE_5D"] = data["MA20"] / data["MA20"].shift(5) - 1
    data["MA50_SLOPE_10D"] = data["MA50"] / data["MA50"].shift(10) - 1
    data["RSI_CHANGE_5D"] = data["RSI14"] - data["RSI14"].shift(5)
    data["MACD_HISTOGRAM_CHANGE_5D"] = (
        data["MACD_HISTOGRAM"] - data["MACD_HISTOGRAM"].shift(5)
    )
    data["VOLUME_TREND_20D"] = data["AVERAGE_VOLUME_5"] / data["AVERAGE_VOLUME_20"] - 1
    data["VOLATILITY_20D"] = data["Close"].pct_change().rolling(window=20).std()
    data["VOLATILITY_REGIME"] = data["VOLATILITY_20D"].apply(classify_volatility_regime)
    data["DAYS_ABOVE_MA20"], data["DAYS_BELOW_MA20"] = build_ma20_streaks(data)
    computed_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    records = []
    for current_index in range(len(data)):
        current = data.iloc[current_index]
        history = data.iloc[: current_index + 1]
        records.append(
            {
                "ticker": ticker.upper(),
                "date": data.index[current_index].date().isoformat(),
                "price_provider": price_provider,
                "close": safe_float(current["Close"]),
                "volume": safe_float(current["Volume"]),
                "ma5": safe_float(current["MA5"]),
                "ma10": safe_float(current["MA10"]),
                "ma20": safe_float(current["MA20"]),
                "ma50": safe_float(current["MA50"]),
                "ma200": safe_float(current["MA200"]),
                "rsi_14": safe_float(current["RSI14"]),
                "macd": safe_float(current["MACD"]),
                "macd_signal": safe_float(current["MACD_SIGNAL"]),
                "macd_histogram": safe_float(current["MACD_HISTOGRAM"]),
                "drawdown_from_20d_high": safe_float(current["DRAWDOWN_FROM_20D_HIGH"]),
                "drawdown_from_60d_high": safe_float(current["DRAWDOWN_FROM_60D_HIGH"]),
                "ma20_slope_5d": safe_float(current["MA20_SLOPE_5D"]),
                "ma50_slope_10d": safe_float(current["MA50_SLOPE_10D"]),
                "rsi_change_5d": safe_float(current["RSI_CHANGE_5D"]),
                "macd_histogram_change_5d": safe_float(
                    current["MACD_HISTOGRAM_CHANGE_5D"]
                ),
                "days_above_ma20": safe_int(current["DAYS_ABOVE_MA20"]),
                "days_below_ma20": safe_int(current["DAYS_BELOW_MA20"]),
                "volume_trend_20d": safe_float(current["VOLUME_TREND_20D"]),
                "volatility_regime": current["VOLATILITY_REGIME"],
                "short_term_trend": classify_short_term_trend(
                    close=safe_float(current["Close"]),
                    ma10=safe_float(current["MA10"]),
                    ma20=safe_float(current["MA20"]),
                ),
                "momentum_state": classify_momentum_state(
                    rsi14=safe_float(current["RSI14"]),
                    macd_histogram=safe_float(current["MACD_HISTOGRAM"]),
                ),
                "is_breakout": is_breakout(history),
                "is_volume_surge": is_volume_surge(current),
                "is_pullback": is_pullback(current),
                "feature_version": feature_version,
                "computed_at": computed_at,
            }
        )

    return records


def normalize_daily_price_frame(price_data: pd.DataFrame) -> pd.DataFrame:
    normalized = price_data.copy()

    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.set_index("date")

    column_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    normalized = normalized.rename(columns=column_map)
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()

    required_columns = ["Close", "Volume"]
    if any(column not in normalized.columns for column in required_columns):
        return pd.DataFrame()

    return normalized


def classify_short_term_trend(
    *,
    close: float | None,
    ma10: float | None,
    ma20: float | None,
) -> str:
    if close is None or ma10 is None or ma20 is None:
        return "unknown"

    if close > ma10 > ma20:
        return "strong"

    if close < ma10 < ma20:
        return "weak"

    return "neutral"


def classify_momentum_state(
    *,
    rsi14: float | None,
    macd_histogram: float | None,
) -> str:
    if rsi14 is None or macd_histogram is None:
        return "unknown"

    if rsi14 >= 70 and macd_histogram > 0:
        return "bullish_but_overbought"

    if rsi14 <= 30 and macd_histogram < 0:
        return "bearish_but_oversold"

    if macd_histogram > 0 and rsi14 >= 55:
        return "bullish_momentum"

    if macd_histogram < 0 and rsi14 <= 45:
        return "bearish_momentum"

    if macd_histogram > 0:
        return "turning_positive"

    if macd_histogram < 0:
        return "turning_negative"

    return "neutral"


def is_breakout(history: pd.DataFrame, lookback_days: int = 20) -> bool:
    if len(history) <= lookback_days:
        return False

    recent_data = history.tail(lookback_days + 1)
    latest_close = float(recent_data["Close"].iloc[-1])
    previous_high = float(recent_data["Close"].iloc[:-1].max())
    return bool(latest_close > previous_high)


def is_volume_surge(current: pd.Series, surge_multiplier: float = 1.5) -> bool:
    average_volume = safe_float(current["AVERAGE_VOLUME_20"])
    latest_volume = safe_float(current["Volume"])

    if not average_volume or latest_volume is None:
        return False

    return bool(latest_volume / average_volume >= surge_multiplier)


def is_pullback(current: pd.Series, tolerance: float = 0.03) -> bool:
    close = safe_float(current["Close"])
    ma20 = safe_float(current["MA20"])

    if close is None or ma20 is None or ma20 == 0:
        return False

    distance_from_ma20 = (close - ma20) / ma20
    return bool(abs(distance_from_ma20) <= tolerance and distance_from_ma20 >= -tolerance)


def build_ma20_streaks(data: pd.DataFrame) -> tuple[list[int], list[int]]:
    days_above = []
    days_below = []
    above_count = 0
    below_count = 0

    for _, current in data.iterrows():
        close = safe_float(current["Close"])
        ma20 = safe_float(current["MA20"])
        if close is None or ma20 is None:
            above_count = 0
            below_count = 0
        elif close > ma20:
            above_count += 1
            below_count = 0
        elif close < ma20:
            below_count += 1
            above_count = 0
        else:
            above_count = 0
            below_count = 0

        days_above.append(above_count)
        days_below.append(below_count)

    return days_above, days_below


def classify_volatility_regime(volatility_20d) -> str:
    volatility = safe_float(volatility_20d)
    if volatility is None:
        return "unknown"
    if volatility < 0.015:
        return "low"
    if volatility < 0.04:
        return "normal"
    return "high"


def safe_float(value) -> float | None:
    if pd.isna(value):
        return None

    return float(value)


def safe_int(value) -> int | None:
    if pd.isna(value):
        return None

    return int(value)
