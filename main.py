from agent.rule_based_router import detect_intent
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


    user_query = input("請輸入你的問題：")
    route_result = detect_intent(user_query)

    print()
    print("Router 判斷結果：")
    print(route_result)

    intent = route_result["intent"]

    if intent == "single_stock_analysis":
        print("這是單一股票分析問題，接下來會要求你輸入股票代號。")
    elif intent == "industry_trend":
        print("這是產業趨勢問題，目前會先用單一股票流程暫時測試。")
    elif intent == "backtest_query":
        print("這是回測查詢問題，接下來會顯示目前已有的 pullback 回測結果。")
    else:
        print("目前無法判斷問題類型，先用單一股票流程暫時測試。")

    ticker = input("請輸入股票代號（例如：MU）：").upper()

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
    print(f"{ticker} 近期新聞：")
    news_items = get_stock_news(f"{ticker} stock", max_items=3)

    for news in news_items:
        print(f"- {news['published']}")
        print(f"  {news['title']}")
        print(f"  {news['link']}")

if __name__ == "__main__":
    main()