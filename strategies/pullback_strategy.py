# 負責判斷多頭趨勢中目前價格是否形成 MA20 回檔訊號

import pandas as pd

def check_pullback_to_ma20(
    price_data: pd.DataFrame,
    tolerance: float = 0.03,
) -> dict:
    data = price_data.copy()

    data["MA20"] = data["Close"].rolling(window=10).mean()

    latest = data.iloc[-1]

    current_price = float(latest["Close"])
    ma20 = float(latest["MA20"])

    distance_from_ma20 = float((current_price - ma20) / ma20)
    
    is_near_ma20 = bool(abs(distance_from_ma20) <= tolerance)
    is_above_or_near_ma20 = bool(distance_from_ma20 >= -tolerance)

    is_pullback = bool(is_near_ma20 and is_above_or_near_ma20)

    return{
        "current_price": round(current_price, 2),
        "ma20": round(ma20, 2),
        "distance_from_ma20": round(distance_from_ma20, 4),
        "tolerance": tolerance,
        "is_near_ma20": is_near_ma20,
        "is_above_or_near_ma20": is_above_or_near_ma20,
        "is_pullback": is_pullback,
    }