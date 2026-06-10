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


def run_single_stock_analysis(ticker: str, user_query: str) -> dict:
    price_data = get_recent_price_data(ticker, period="1y")

    analysis_result = analyze_moving_averages(price_data)
    breakout_result = check_breakout(price_data)
    volume_surge_result = check_volume_surge(price_data)
    pullback_result = check_pullback_to_ma20(price_data)
    news_items = get_stock_news(f"{ticker} stock", max_items=3)

    analysis_data = {
        "intent": "single_stock_analysis",
        "query": user_query,
        "ticker": ticker,
        "technical_analysis": analysis_result,
        "signals": {
            "breakout": breakout_result,
            "volume_surge": volume_surge_result,
            "pullback": pullback_result,
        },
        "news": news_items,
    }

    return analysis_data


def run_backtest_query(ticker: str, user_query: str) -> dict:
    query = user_query.lower()

    if "breakout" in query or "突破" in user_query:
        strategy = "breakout"
    elif "volume" in query or "成交量" in user_query or "量能" in user_query:
        strategy = "volume_surge"
    elif "pullback" in query or "回檔" in user_query or "拉回" in user_query:
        strategy = "pullback"
    else:
        strategy = "unknown"

    if strategy != "pullback":
        return {
            "intent": "backtest_query",
            "ticker": ticker,
            "strategy": strategy,
            "user_query": user_query,
            "status": "unsupported_strategy",
            "message": "目前第 9 關先只支援 pullback 策略回測。",
        }

    price_data = get_recent_price_data(ticker, period="2y")

    backtest_results = run_pullback_backtest(price_data)
    metrics = calculate_backtest_metrics(backtest_results)

    report = build_backtest_report(
        ticker=ticker,
        strategy_name="pullback",
        backtest_results=backtest_results,
        metrics=metrics,
    )

    report_text = format_backtest_report(report)

    backtest_data = {
        "intent": "backtest_query",
        "ticker": ticker,
        "strategy": strategy,
        "user_query": user_query,
        "status": "success",
        "report": report,
        "report_text": report_text,
    }

    return backtest_data


def print_analysis_data(analysis_data: dict) -> None:
    print()
    print("Analysis Data Summary")
    print("---------------------")

    print("Ticker:", analysis_data["ticker"])
    print("Intent:", analysis_data["intent"])
    print("Query:", analysis_data["query"])

    print()
    print("Technical Analysis:")
    print(analysis_data["technical_analysis"])

    print()
    print("Signals:")
    print("Breakout:", analysis_data["signals"]["breakout"])
    print("Volume Surge:", analysis_data["signals"]["volume_surge"])
    print("Pullback:", analysis_data["signals"]["pullback"])

    print()
    print("Recent News:")
    for news in analysis_data["news"]:
        print("-", news["published"])
        print(" ", news["title"])
        print(" ", news["link"])


def print_backtest_data(backtest_data: dict) -> None:
    print()
    print("Backtest Data Summary")
    print("---------------------")

    print("Intent:", backtest_data["intent"])
    print("Ticker:", backtest_data["ticker"])
    print("Strategy:", backtest_data["strategy"])
    print("Query:", backtest_data["user_query"])
    print("Status:", backtest_data["status"])

    if backtest_data["status"] != "success":
        print("Message:", backtest_data["message"])
        return

    print()
    print(backtest_data["report_text"])

    print()
    print("Sample Trades:")
    for trade in backtest_data["report"]["sample_trades"]:
        print(trade)


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
        ticker = input("請輸入股票代號（例如：MU）：").upper()
        analysis_data = run_single_stock_analysis(ticker, user_query)
        print_analysis_data(analysis_data)

    elif intent == "backtest_query":
        ticker = input("請輸入要回測的股票代號（例如：MU）：").upper()
        backtest_data = run_backtest_query(ticker, user_query)
        print_backtest_data(backtest_data)

    else:
        print()
        print("目前這個 intent 還沒有完整 workflow")
        print("偵測到的 intent：", intent)


if __name__ == "__main__":
    main()
