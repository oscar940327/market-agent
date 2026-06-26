# 負責分析資料

import pandas as pd


def calculate_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.rolling(window=window).mean()
    average_loss = losses.rolling(window=window).mean()
    relative_strength = average_gain / average_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + relative_strength))

    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100)
    rsi = rsi.mask((average_gain == 0) & (average_loss > 0), 0)
    rsi = rsi.mask((average_gain == 0) & (average_loss == 0), 50)

    return rsi.fillna(50)


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_histogram = macd - macd_signal
    return macd, macd_signal, macd_histogram


def classify_momentum_state(rsi14: float, macd_histogram: float) -> str:
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


def analyze_moving_averages(price_data: pd.DataFrame) -> dict:
    data = price_data.copy()

    data["MA10"] = data["Close"].rolling(window=10).mean()
    data["MA20"] = data["Close"].rolling(window=20).mean()
    data["MA50"] = data["Close"].rolling(window=50).mean()
    data["RSI14"] = calculate_rsi(data["Close"], window=14)
    data["MACD"], data["MACD_SIGNAL"], data["MACD_HISTOGRAM"] = calculate_macd(
        data["Close"]
    )

    latest = data.iloc[-1]

    current_price = float(latest["Close"])
    ma10 = float(latest["MA10"])
    ma20 = float(latest["MA20"])
    ma50 = float(latest["MA50"])
    rsi14 = float(latest["RSI14"])
    macd = float(latest["MACD"])
    macd_signal = float(latest["MACD_SIGNAL"])
    macd_histogram = float(latest["MACD_HISTOGRAM"])

    is_above_ma20 = bool(current_price > ma20)

    if current_price > ma10 > ma20:
        short_term_trend = "strong"
    elif current_price < ma10 < ma20:
        short_term_trend = "weak"
    else:
        short_term_trend = "neutral"

    return {
        "current_price": round(current_price, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "is_above_ma20": is_above_ma20,
        "short_term_trend": short_term_trend,
        "rsi14": round(rsi14, 2),
        "macd": round(macd, 4),
        "macd_signal": round(macd_signal, 4),
        "macd_histogram": round(macd_histogram, 4),
        "momentum_state": classify_momentum_state(rsi14, macd_histogram),
    }
