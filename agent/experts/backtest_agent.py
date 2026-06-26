from backtesting.backtest_runner import (
    run_breakout_backtest,
    run_pullback_backtest,
    run_volume_surge_backtest,
)
from backtesting.metrics import calculate_backtest_metrics
from backtesting.reports import build_backtest_report
from backtesting.evidence import build_backtest_evidence_quality


def select_backtest_strategy(user_query: str) -> str:
    query = user_query.lower()

    if "breakout" in query or "突破" in user_query:
        return "breakout"

    if (
        "volume" in query
        or "成交量" in user_query
        or "量能" in user_query
        or "放量" in user_query
    ):
        return "volume_surge"

    if "pullback" in query or "回檔" in user_query or "拉回" in user_query:
        return "pullback"

    return "unknown"


def run_backtest_agent(
    ticker: str,
    user_query: str,
    price_data,
    data_window: dict | None = None,
) -> dict:
    strategy = select_backtest_strategy(user_query)

    if strategy == "unknown":
        return {
            "agent": "backtest",
            "status": "unknown_strategy",
            "strategy": strategy,
            "message": "請指定要回測的策略：breakout、volume_surge 或 pullback。",
        }

    if strategy == "breakout":
        backtest_results = run_breakout_backtest(price_data)
    elif strategy == "volume_surge":
        backtest_results = run_volume_surge_backtest(price_data)
    else:
        backtest_results = run_pullback_backtest(price_data)

    metrics = calculate_backtest_metrics(backtest_results)
    evidence_quality = build_backtest_evidence_quality(
        metrics=metrics,
        data_window=data_window or {},
    )
    report = build_backtest_report(
        ticker=ticker,
        strategy_name=strategy,
        backtest_results=backtest_results,
        metrics=metrics,
        evidence_quality=evidence_quality,
        data_window=data_window,
    )

    return {
        "agent": "backtest",
        "status": "success",
        "strategy": strategy,
        "metrics": metrics,
        "evidence_quality": evidence_quality,
        "data_window": data_window,
        "report": report,
        "summary": {
            "total_trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "average_return": metrics["average_return"],
            "max_loss": metrics["max_loss"],
            "evidence_level": evidence_quality["level"],
        },
    }
