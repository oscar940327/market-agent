from backtesting.evidence import build_backtest_evidence_quality
from strategies.breakout_strategy import check_breakout
from strategies.pullback_strategy import check_pullback_to_ma20
from strategies.volume_surge_strategy import check_volume_surge


HORIZONS = (5, 10, 20)

SIGNAL_DEFINITIONS = {
    "breakout": {
        "label": "突破訊號",
        "trigger_key": "is_breakout",
        "min_index": 20,
        "checker": lambda data: check_breakout(data),
    },
    "volume_surge": {
        "label": "放量訊號",
        "trigger_key": "is_volume_surge",
        "min_index": 20,
        "checker": lambda data: check_volume_surge(data),
    },
    "pullback": {
        "label": "回踩訊號",
        "trigger_key": "is_pullback",
        "min_index": 50,
        "checker": lambda data: check_pullback_to_ma20(data),
    },
}


def build_signal_backtest_evidence(
    *,
    ticker: str,
    price_data,
    current_signals: dict,
    data_window: dict,
) -> dict:
    triggered_strategies = get_triggered_strategies(current_signals)

    if not triggered_strategies:
        return {
            "status": "no_triggered_signals",
            "ticker": ticker,
            "data_window": data_window,
            "signals": [],
            "summary": {
                "triggered_signal_count": 0,
                "message": "目前沒有明確突破、放量或回踩訊號，因此本次不附加歷史訊號參考。",
            },
        }

    signals = [
        build_strategy_signal_evidence(
            ticker=ticker,
            strategy=strategy,
            price_data=price_data,
            data_window=data_window,
        )
        for strategy in triggered_strategies
    ]

    return {
        "status": "success",
        "ticker": ticker,
        "data_window": data_window,
        "signals": signals,
        "summary": {
            "triggered_signal_count": len(signals),
            "strategies": [signal["strategy"] for signal in signals],
            "best_evidence_level": pick_best_evidence_level(signals),
        },
    }


def get_triggered_strategies(current_signals: dict) -> list[str]:
    triggered = []

    for strategy, definition in SIGNAL_DEFINITIONS.items():
        signal = current_signals.get(strategy, {})
        if signal.get(definition["trigger_key"]):
            triggered.append(strategy)

    return triggered


def build_strategy_signal_evidence(
    *,
    ticker: str,
    strategy: str,
    price_data,
    data_window: dict,
) -> dict:
    definition = SIGNAL_DEFINITIONS[strategy]
    event_indices = collect_signal_event_indices(
        price_data=price_data,
        strategy=strategy,
    )
    horizons = {
        str(horizon): build_horizon_metrics(
            price_data=price_data,
            event_indices=event_indices,
            horizon=horizon,
        )
        for horizon in HORIZONS
    }

    primary_metrics = build_primary_metrics(horizons)
    sampling_policy = {
        "allow_overlapping": False,
        "cooldown_trading_days": max(HORIZONS),
        "description": "每次訊號後間隔 20 個交易日，再計入下一個歷史樣本。",
    }
    evidence_quality = build_backtest_evidence_quality(
        metrics=primary_metrics,
        data_window=data_window,
        sampling_policy=sampling_policy,
    )

    return {
        "ticker": ticker,
        "strategy": strategy,
        "label": definition["label"],
        "triggered": True,
        "sample_size": primary_metrics["total_trades"],
        "horizons": horizons,
        "average_return": primary_metrics["average_return"],
        "max_loss": primary_metrics["max_loss"],
        "primary_horizon_days": 20,
        "sampling_policy": sampling_policy,
        "evidence_quality": evidence_quality,
    }


def collect_signal_event_indices(*, price_data, strategy: str) -> list[int]:
    definition = SIGNAL_DEFINITIONS[strategy]
    event_indices = []
    min_index = definition["min_index"]
    max_horizon = max(HORIZONS)
    next_eligible_index = min_index

    for current_index in range(min_index, len(price_data) - max_horizon):
        if current_index < next_eligible_index:
            continue
        historical_data = price_data.iloc[: current_index + 1]
        signal = definition["checker"](historical_data)

        if signal.get(definition["trigger_key"]):
            event_indices.append(current_index)
            next_eligible_index = current_index + max_horizon

    return event_indices


def build_horizon_metrics(*, price_data, event_indices: list[int], horizon: int) -> dict:
    returns = [
        calculate_forward_return(price_data, current_index, horizon)
        for current_index in event_indices
        if current_index + horizon < len(price_data)
    ]

    if not returns:
        return {
            "horizon_days": horizon,
            "sample_size": 0,
            "win_rate": 0,
            "average_return": 0,
            "max_loss": 0,
        }

    wins = [return_pct for return_pct in returns if return_pct > 0]

    return {
        "horizon_days": horizon,
        "sample_size": len(returns),
        "win_rate": round(len(wins) / len(returns), 4),
        "average_return": round(sum(returns) / len(returns), 4),
        "max_loss": round(min(returns), 4),
    }


def calculate_forward_return(price_data, current_index: int, horizon: int) -> float:
    entry_price = float(price_data["Close"].iloc[current_index])
    exit_price = float(price_data["Close"].iloc[current_index + horizon])
    return float((exit_price - entry_price) / entry_price)


def build_primary_metrics(horizons: dict) -> dict:
    primary = horizons["20"]
    max_loss = min(horizon["max_loss"] for horizon in horizons.values())

    return {
        "total_trades": primary["sample_size"],
        "win_rate": primary["win_rate"],
        "average_return": primary["average_return"],
        "max_loss": max_loss,
    }


def pick_best_evidence_level(signals: list[dict]) -> str:
    levels = ["none", "low", "low_to_medium", "medium", "high"]
    best_level = "none"

    for signal in signals:
        level = signal["evidence_quality"]["level"]
        if levels.index(level) > levels.index(best_level):
            best_level = level

    return best_level
