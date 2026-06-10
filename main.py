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

        print()
        print("Analysis Data:")
        print(analysis_data)

    else:
        print()
        print("目前這個 intent 還沒有完整 workflow")
        print("偵測到的 intent：", intent)


if __name__ == "__main__":
    main()


