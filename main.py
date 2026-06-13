from agent.rule_based_router import detect_intent
from agent.market_manager import (
    MarketManagerAgent,
    fetch_price_data,
    validate_price_data,
)
from agent.reporting import build_report, get_default_analyst_mode
from data.themes import find_theme_key, get_all_theme_tickers, get_theme


market_manager = MarketManagerAgent()


def run_single_stock_analysis(
    ticker: str,
    user_query: str,
    include_news: bool = True,
    include_fundamentals: bool = True,
) -> dict:
    return market_manager.run_single_stock_analysis(
        ticker=ticker,
        user_query=user_query,
        include_news=include_news,
        include_fundamentals=include_fundamentals,
    )


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
            include_fundamentals=False,
        )
        results.append(score_stock_analysis(analysis_data))

    sorted_results = sorted(
        results,
        key=lambda item: item["score"],
        reverse=True,
    )
    sector_summary = build_sector_summary(sorted_results)

    return {
        "intent": "industry_trend",
        "status": "success",
        "query": user_query,
        "theme_key": theme_key,
        "theme_name": theme_name,
        "sector_summary": sector_summary,
        "results": sorted_results,
    }


def build_sector_summary(results: list[dict]) -> dict:
    successful_results = [result for result in results if result["status"] == "success"]

    if not successful_results:
        return {
            "successful_count": 0,
            "average_score": 0,
            "strongest_ticker": None,
            "positive_breadth": 0,
            "breadth_label": "no_data",
        }

    positive_results = [result for result in successful_results if result["score"] > 0]
    average_score = sum(result["score"] for result in successful_results) / len(
        successful_results
    )
    positive_breadth = len(positive_results) / len(successful_results)
    strongest_result = successful_results[0]

    return {
        "successful_count": len(successful_results),
        "average_score": round(average_score, 2),
        "strongest_ticker": strongest_result["ticker"],
        "positive_breadth": round(positive_breadth, 4),
        "breadth_label": classify_sector_breadth(positive_breadth),
    }


def classify_sector_breadth(positive_breadth: float) -> str:
    if positive_breadth >= 0.7:
        return "broad_strength"

    if positive_breadth >= 0.4:
        return "mixed"

    return "weak_breadth"


def run_backtest_query(ticker: str, user_query: str) -> dict:
    return market_manager.run_backtest_query(ticker=ticker, user_query=user_query)


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
        report_result = build_report(
            kind="single_stock",
            data=analysis_data,
            analyst_mode=get_default_analyst_mode(),
        )
        print()
        print(report_result["report"])

    elif intent == "backtest_query":
        ticker = input("請輸入要回測的股票代號（例如：MU）：").upper()
        backtest_data = run_backtest_query(ticker, user_query)
        report_result = build_report(
            kind="backtest",
            data=backtest_data,
            analyst_mode=get_default_analyst_mode(),
        )
        print()
        print(report_result["report"])

    elif intent == "industry_trend":
        theme_data = run_theme_analysis(user_query)
        report_result = build_report(
            kind="theme",
            data=theme_data,
            analyst_mode=get_default_analyst_mode(),
        )
        print()
        print(report_result["report"])

    else:
        print()
        print("目前這個 intent 還沒有完整 workflow")
        print("偵測到的 intent：", intent)


if __name__ == "__main__":
    main()
