from skills.news_analysis_skill import analyze_news_items
from skills.news_skill import get_stock_news


def fetch_news_items(ticker: str) -> list[dict]:
    try:
        return get_stock_news(f"{ticker} stock", max_items=3)
    except Exception:
        return []


def run_news_agent(ticker: str, include_news: bool = True) -> dict:
    news_items = []

    if include_news:
        news_items = fetch_news_items(ticker)

    news_analysis = analyze_news_items(news_items)
    summary = news_analysis["summary"]

    return {
        "agent": "news",
        "status": "success",
        "news": news_items,
        "news_analysis": news_analysis,
        "summary": {
            "sentiment": summary["sentiment"],
            "total_items": summary["total_items"],
            "top_topics": summary["top_topics"],
            "high_importance_count": summary["high_importance_count"],
        },
    }
