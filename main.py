from skills.stock_price_skill import get_recent_price_data
from skills.technical_analysis_skill import analyze_moving_averages
from strategies.breakout_strategy import check_breakout
from strategies.volume_surge_strategy import check_volume_surge
from strategies.pullback_strategy import check_pullback_to_ma20
from backtesting.backtest_runner import run_pullback_backtest


def main():
    print("Market Agent")
    print("Project skeleton is ready.")
    print()

    ticker = input("請輸入股票代號（例如：MU）：")

    price_data = get_recent_price_data(ticker)
    analysis_result = analyze_moving_averages(price_data)
    breakout_result = check_breakout(price_data)
    volume_surge_result = check_volume_surge(price_data)
    pullback_result = check_pullback_to_ma20(price_data)
    backtest_results = run_pullback_backtest(price_data)

    print()
    print(f"{ticker} 技術分析結果：")
    print(analysis_result) 

    print()
    print(f"{ticker} 突破策略結果：")
    print(breakout_result)

    print()
    print(f"{ticker} 成交量放大策略結果：")
    print(volume_surge_result)

    print()
    print(f"{ticker} Pullback 策略結果：")
    print(pullback_result)

    print()
    print(f"{ticker} Pullback 回測結果，前 5 筆：")
    print(backtest_results[:5])

    print()
    print(f"總訊號數：{len(backtest_results)}")

if __name__ == "__main__":
    main()