# 負責用歷史股價資料回測策略訊號，計算每次訊號出現後的報酬

import pandas as pd

from strategies.breakout_strategy import check_breakout
from strategies.pullback_strategy import check_pullback_to_ma20
from strategies.volume_surge_strategy import check_volume_surge


def build_trade_result(
    price_data: pd.DataFrame,
    current_index: int,
    holding_days: int,
) -> dict:
    entry_price = float(price_data["Close"].iloc[current_index])
    exit_price = float(price_data["Close"].iloc[current_index + holding_days])

    return_pct = float((exit_price - entry_price) / entry_price)

    return {
        "signal_date": str(price_data.index[current_index].date()),
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "holding_days": holding_days,
        "return_pct": round(return_pct, 4),
    }


def run_breakout_backtest(
    price_data: pd.DataFrame,
    holding_days: int = 5,
    lookback_days: int = 20,
) -> list[dict]:
    results = []
    next_eligible_index = lookback_days

    for current_index in range(lookback_days, len(price_data) - holding_days):
        if current_index < next_eligible_index:
            continue
        historical_data = price_data.iloc[: current_index + 1]

        signal = check_breakout(
            historical_data,
            lookback_days=lookback_days,
        )

        if signal["is_breakout"]:
            results.append(
                build_trade_result(
                    price_data=price_data,
                    current_index=current_index,
                    holding_days=holding_days,
                )
            )
            next_eligible_index = current_index + holding_days

    return results


def run_pullback_backtest(
    price_data: pd.DataFrame,
    holding_days: int = 5,
) -> list[dict]:
    results = []
    next_eligible_index = 50

    for current_index in range(50, len(price_data) - holding_days):
        if current_index < next_eligible_index:
            continue
        historical_data = price_data.iloc[: current_index + 1]

        signal = check_pullback_to_ma20(historical_data)

        if signal["is_pullback"]:
            results.append(
                build_trade_result(
                    price_data=price_data,
                    current_index=current_index,
                    holding_days=holding_days,
                )
            )
            next_eligible_index = current_index + holding_days

    return results


def run_volume_surge_backtest(
    price_data: pd.DataFrame,
    holding_days: int = 5,
    lookback_days: int = 20,
    surge_multiplier: float = 1.5,
) -> list[dict]:
    results = []
    next_eligible_index = lookback_days

    for current_index in range(lookback_days, len(price_data) - holding_days):
        if current_index < next_eligible_index:
            continue
        historical_data = price_data.iloc[: current_index + 1]

        signal = check_volume_surge(
            historical_data,
            lookback_days=lookback_days,
            surge_multiplier=surge_multiplier,
        )

        if signal["is_volume_surge"]:
            results.append(
                build_trade_result(
                    price_data=price_data,
                    current_index=current_index,
                    holding_days=holding_days,
                )
            )
            next_eligible_index = current_index + holding_days

    return results
