# 負責計算回測績效指標

def calculate_backtest_metrics(backtest_results: list[dict]) -> dict:
    total_trades = len(backtest_results)

    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "average_return": 0,
            "max_loss": 0,
        }
    
    returns = [result["return_pct"] for result in backtest_results]

    winning_trades = [return_pct for return_pct in returns if return_pct > 0]

    win_rate = float(len(winning_trades) / total_trades)
    average_return = float(sum(returns) / total_trades)
    max_loss = float(min(returns))

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "average_return": round(average_return, 4),
        "max_loss": round(max_loss, 4),   
    }