# 最新收盤價 > 過去 20 日最高收盤價

import pandas as pd

def check_breakout(price_data: pd.DataFrame, lookback_days: int = 20) -> dict:
    data = price_data.copy()

    recent_data = data.tail(lookback_days + 1)

    latest_close = float(recent_data["Close"].iloc[-1])
    previous_high = float(recent_data["Close"].iloc[:-1].max())

    is_breakout = bool(latest_close > previous_high)

    return {
        "lookback_days": lookback_days,
        "latest_close": round(latest_close, 2),
        "previous_high": round(previous_high, 2),
        "is_breakout": is_breakout,
    }