# 負責分析資料

import pandas as pd 

def analyze_moving_averages(price_data: pd.DataFrame) -> dict:
    data = price_data.copy()

    data["MA10"] = data["Close"].rolling(window=10).mean()
    data["MA20"] = data["Close"].rolling(window=20).mean()
    data["MA50"] = data["Close"].rolling(window=50).mean()

    latest = data.iloc[-1]

    current_price = float(latest["Close"]) 
    ma10 = float(latest["MA10"])
    ma20 = float(latest["MA20"])
    ma50 = float(latest["MA50"])

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
    }