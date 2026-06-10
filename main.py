from skills.stock_price_skill import get_recent_price_data
from skills.technical_analysis_skill import analyze_moving_averages
from skills.news_skill import get_stock_news
from strategies.breakout_strategy import check_breakout
from strategies.volume_surge_strategy import check_volume_surge
from strategies.pullback_strategy import check_pullback_to_ma20
from backtesting.backtest_runner import run_pullback_backtest
from backtesting.metrics import calculate_backtest_metrics
from backtesting.reports import build_backtest_report, format_backtest_report


def main():
    print("Market Agent")
    print("Project skeleton is ready.")
    print()

    ticker = input("請輸入股票代號（例如：MU）：")

    price_data = get_recent_price_data(ticker, period="1y")

    analysis_result = analyze_moving_averages(price_data)
    breakout_result = check_breakout(price_data)
    volume_surge_result = check_volume_surge(price_data)
    pullback_result = check_pullback_to_ma20(price_data)

    backtest_results = run_pullback_backtest(price_data)
    backtest_metrics = calculate_backtest_metrics(backtest_results)
    backtest_report = build_backtest_report(
        ticker=ticker,
        strategy_name="pullback_to_ma20",
        backtest_results=backtest_results,
        metrics=backtest_metrics,
    )
    formatted_report = format_backtest_report(backtest_report)

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
    print(f"{ticker} Pullback 回測報告：")
    print(formatted_report)

    print()
    news_items = get_stock_news(f"{ticker} stock", max_items=3)

    for news in news_items:
        print(f"- {news['published']}")
        print(f"  {news['title']}")
        print(f"  {news['link']}")

if __name__ == "__main__":
    main()