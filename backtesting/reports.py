# 輸出回測報告

def build_backtest_report(
    ticker: str,
    strategy_name: str,
    backtest_results: list[dict],
    metrics: dict,
) -> dict:
    return{
        "ticker": ticker,
        "strategy_name": strategy_name,
        "metrics": metrics,
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