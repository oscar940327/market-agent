# 負責用歷史股價資料回測 pullback_strategy，計算每次 pullback 訊號出現後的報酬

import pandas as pd

from strategies.pullback_strategy import check_pullback_to_ma20

def run_pullback_backtest(
    price_data: pd.DataFrame,
    holding_days: int = 5,
) -> list[dict]:
    results = []

    for current_index in range(50, len(price_data) - holding_days):
        historical_data = price_data.iloc[: current_index + 1]

        signal = check_pullback_to_ma20(historical_data)

        if signal["is_pullback"]:
            entry_price = float(price_data["Close"].iloc[current_index])
            exit_price = float(price_data["Close"].iloc[current_index + holding_days])

            return_pct = float((exit_price - entry_price) / entry_price)
            
            results.append(
                {
                    "signal_date": str(price_data.index[current_index].date()),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "holding_days": holding_days,
                    "return_pct": round(return_pct, 4),
                }
            )

    return results