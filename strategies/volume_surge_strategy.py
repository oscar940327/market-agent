# 最新成交量是否明顯大於過去平均成交量

import pandas as pd

def check_volume_surge(
    price_data: pd.DataFrame,
    lookback_days: int = 20,
    surge_multiplier: float = 1.5,
) -> dict:
    data =  price_data.copy()

    recent_data = data.tail(lookback_days + 1)

    latest_volume = float(recent_data["Volume"].iloc[-1])
    average_volume = float(recent_data["Volume"].iloc[:-1].mean())

    volume_ratio = float(latest_volume / average_volume)

    is_volume_surge = bool(volume_ratio >= surge_multiplier)

    return {
        "lookback_days": lookback_days,
        "surge_multiplier": surge_multiplier,
        "latest_volume": int(latest_volume),
        "average_volume": int(average_volume),
        "volume_ratio": round(volume_ratio, 2),
        "is_volume_surge": is_volume_surge,
    }