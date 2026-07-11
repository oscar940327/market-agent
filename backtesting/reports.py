# 輸出回測報告

def build_backtest_report(
    ticker: str,
    strategy_name: str,
    backtest_results: list[dict],
    metrics: dict,
    evidence_quality: dict | None = None,
    data_window: dict | None = None,
    sampling_policy: dict | None = None,
) -> dict:
    return{
        "ticker": ticker,
        "strategy_name": strategy_name,
        "metrics": metrics,
        "evidence_quality": evidence_quality,
        "data_window": data_window,
        "sampling_policy": sampling_policy or {},
        "sample_trades": backtest_results[:5],
    }

def format_backtest_report(report: dict) -> str:
    metrics = report["metrics"]

    return (
        f"Backtest Report: {report['ticker']} - {report['strategy_name']}\n"
        f"Total Trades: {metrics['total_trades']}\n"
        f"Win Rate: {metrics['win_rate'] * 100:.2f}%\n"
        f"Average Return: {metrics['average_return'] * 100:.2f}%\n"
        f"Max Loss: {metrics['max_loss'] * 100:.2f}%"
    )
