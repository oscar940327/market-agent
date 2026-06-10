from agent.rule_based_router import detect_intent
from agent.analyst import (
    format_backtest_analysis,
    format_single_stock_analysis,
    format_theme_analysis,
)
from data.themes import find_theme_key, get_all_theme_tickers, get_theme
from skills.stock_price_skill import get_recent_price_data
from skills.technical_analysis_skill import analyze_moving_averages
from skills.news_skill import get_stock_news
from strategies.breakout_strategy import check_breakout
from strategies.volume_surge_strategy import check_volume_surge
from strategies.pullback_strategy import check_pullback_to_ma20
from backtesting.backtest_runner import (
    run_breakout_backtest,
    run_pullback_backtest,
    run_volume_surge_backtest,
)
from backtesting.metrics import calculate_backtest_metrics
from backtesting.reports import build_backtest_report


def validate_price_data(price_data, ticker: str, min_rows: int):
    if price_data is None or price_data.empty:
        return {
            "ticker": ticker,
            "status": "no_price_data",
            "message": "沒有取得股價資料，請確認股票代號是否正確或稍後再試。",
        }

    missing_columns = [
        column for column in ["Close", "Volume"] if column not in price_data.columns
    ]

    if missing_columns:
        return {
            "ticker": ticker,
            "status": "invalid_price_data",
            "message": f"股價資料缺少必要欄位：{', '.join(missing_columns)}。",
        }

    if len(price_data) < min_rows:
        return {
            "ticker": ticker,
            "status": "not_enough_price_data",
            "message": f"目前只有 {len(price_data)} 筆資料，至少需要 {min_rows} 筆。",
        }

    return None


def fetch_price_data(ticker: str, period: str):
    try:
        return get_recent_price_data(ticker, period=period), None
    except Exception as error:
        return None, {
            "ticker": ticker,
            "status": "price_data_error",
            "message": f"取得股價資料時發生錯誤：{error}",
        }


def fetch_news_items(ticker: str) -> list[dict]:
    try:
        return get_stock_news(f"{ticker} stock", max_items=3)
    except Exception:
        return []


def run_single_stock_analysis(
    ticker: str,
    user_query: str,
    include_news: bool = True,
) -> dict:
    price_data, fetch_error = fetch_price_data(ticker, period="1y")

    if fetch_error:
        return {
            "intent": "single_stock_analysis",
            "query": user_query,
            **fetch_error,
        }

    data_error = validate_price_data(price_data, ticker=ticker, min_rows=50)

    if data_error:
        return {
            "intent": "single_stock_analysis",
            "query": user_query,
            **data_error,
        }

    analysis_result = analyze_moving_averages(price_data)
    breakout_result = check_breakout(price_data)
    volume_surge_result = check_volume_surge(price_data)
    pullback_result = check_pullback_to_ma20(price_data)
    news_items = []

    if include_news:
        news_items = fetch_news_items(ticker)

    analysis_data = {
        "intent": "single_stock_analysis",
        "status": "success",
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


def score_stock_analysis(analysis_data: dict) -> dict:
    if analysis_data["status"] != "success":
        return {
            "ticker": analysis_data.get("ticker", ""),
            "status": analysis_data["status"],
            "score": 0,
            "reasons": [analysis_data["message"]],
            "analysis": analysis_data,
        }

    score = 0
    reasons = []
    technical = analysis_data["technical_analysis"]
    signals = analysis_data["signals"]

    if technical["short_term_trend"] == "strong":
        score += 2
        reasons.append("短線趨勢偏強")
    elif technical["short_term_trend"] == "weak":
        score -= 1
        reasons.append("短線趨勢偏弱")

    if technical["is_above_ma20"]:
        score += 1
        reasons.append("站上 MA20")
    else:
        score -= 1
        reasons.append("低於 MA20")

    if signals["breakout"]["is_breakout"]:
        score += 2
        reasons.append("出現突破訊號")

    if signals["volume_surge"]["is_volume_surge"]:
        score += 1.5
        reasons.append("成交量放大")

    if signals["pullback"]["is_pullback"]:
        score += 1
        reasons.append("接近 MA20 回測區")

    if not reasons:
        reasons.append("目前訊號偏中性")

    return {
        "ticker": analysis_data["ticker"],
        "status": "success",
        "score": score,
        "reasons": reasons,
        "analysis": analysis_data,
    }


def run_theme_analysis(user_query: str) -> dict:
    theme_key = find_theme_key(user_query)

    if theme_key:
        theme = get_theme(theme_key)
        theme_name = theme["name"]
        tickers = theme["tickers"]
    else:
        theme_name = "全部支援主題"
        tickers = get_all_theme_tickers()

    results = []

    for ticker in tickers:
        analysis_data = run_single_stock_analysis(
            ticker=ticker,
            user_query=user_query,
            include_news=False,
        )
        results.append(score_stock_analysis(analysis_data))

    sorted_results = sorted(
        results,
        key=lambda item: item["score"],
        reverse=True,
    )

    return {
        "intent": "industry_trend",
        "status": "success",
        "query": user_query,
        "theme_key": theme_key,
        "theme_name": theme_name,
        "results": sorted_results,
    }


def run_backtest_query(ticker: str, user_query: str) -> dict:
    query = user_query.lower()

    if "breakout" in query or "突破" in user_query:
        strategy = "breakout"
    elif (
        "volume" in query
        or "成交量" in user_query
        or "量能" in user_query
        or "放量" in user_query
    ):
        strategy = "volume_surge"
    elif "pullback" in query or "回檔" in user_query or "拉回" in user_query:
        strategy = "pullback"
    else:
        strategy = "unknown"

    if strategy == "unknown":
        return {
            "intent": "backtest_query",
            "ticker": ticker,
            "strategy": strategy,
            "user_query": user_query,
            "status": "unknown_strategy",
            "message": "請指定要回測的策略：breakout、volume_surge 或 pullback。",
        }

    price_data, fetch_error = fetch_price_data(ticker, period="2y")

    if fetch_error:
        return {
            "intent": "backtest_query",
            "strategy": strategy,
            "user_query": user_query,
            **fetch_error,
        }

    data_error = validate_price_data(price_data, ticker=ticker, min_rows=60)

    if data_error:
        return {
            "intent": "backtest_query",
            "strategy": strategy,
            "user_query": user_query,
            **data_error,
        }

    if strategy == "breakout":
        backtest_results = run_breakout_backtest(price_data)
    elif strategy == "volume_surge":
        backtest_results = run_volume_surge_backtest(price_data)
    else:
        backtest_results = run_pullback_backtest(price_data)

    metrics = calculate_backtest_metrics(backtest_results)

    report = build_backtest_report(
        ticker=ticker,
        strategy_name=strategy,
        backtest_results=backtest_results,
        metrics=metrics,
    )

    backtest_data = {
        "intent": "backtest_query",
        "ticker": ticker,
        "strategy": strategy,
        "user_query": user_query,
        "status": "success",
        "report": report,
    }

    return backtest_data


def main():
    print("Market Agent")
    print("個人股票研究助理 CLI")
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
        print(format_single_stock_analysis(analysis_data))

    elif intent == "backtest_query":
        ticker = input("請輸入要回測的股票代號（例如：MU）：").upper()
        backtest_data = run_backtest_query(ticker, user_query)
        print()
        print(format_backtest_analysis(backtest_data))

    elif intent == "industry_trend":
        theme_data = run_theme_analysis(user_query)
        print()
        print(format_theme_analysis(theme_data))

    else:
        print()
        print("目前這個 intent 還沒有完整 workflow")
        print("偵測到的 intent：", intent)


if __name__ == "__main__":
    main()
