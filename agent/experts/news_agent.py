from data_store.supabase_store import fetch_news_events
from news_events.summary import build_news_summary
from skills.news_analysis_skill import analyze_news_items
from skills.news_skill import get_stock_news


def fetch_news_event_rows(ticker: str, limit: int = 100) -> list[dict]:
    try:
        return fetch_news_events(ticker=ticker, limit=limit)
    except Exception:
        return []


def fetch_news_items(ticker: str) -> list[dict]:
    try:
        return get_stock_news(f"{ticker} stock", max_items=3)
    except Exception:
        return []


def run_news_agent(ticker: str, include_news: bool = True) -> dict:
    news_items = []
    news_event_rows = []
    news_events_summary = None

    if include_news:
        news_event_rows = fetch_news_event_rows(ticker)
        news_events_summary = build_news_summary(
            ticker=ticker,
            news_events=news_event_rows,
        )
        if news_events_summary["status"] == "success":
            news_analysis = build_news_analysis_from_events_summary(news_events_summary)
            return {
                "agent": "news",
                "status": "success",
                "source": "news_events",
                "news": build_display_news_items(news_events_summary),
                "news_events": news_event_rows,
                "news_events_summary": news_events_summary,
                "news_analysis": news_analysis,
                "summary": build_agent_summary(news_analysis, news_events_summary),
            }

        news_items = fetch_news_items(ticker)

    news_analysis = analyze_news_items(news_items)
    summary = news_analysis["summary"]

    return {
        "agent": "news",
        "status": "success",
        "source": "legacy_news_skill" if include_news else "skipped",
        "news": news_items,
        "news_events": news_event_rows,
        "news_events_summary": news_events_summary,
        "news_analysis": news_analysis,
        "summary": {
            "sentiment": summary["sentiment"],
            "total_items": summary["total_items"],
            "top_topics": summary["top_topics"],
            "high_importance_count": summary["high_importance_count"],
        },
    }


def build_news_analysis_from_events_summary(news_events_summary: dict) -> dict:
    summary = {
        "total_items": news_events_summary["total_events"],
        "sentiment": news_events_summary["overall_sentiment"],
        "sentiment_counts": news_events_summary["sentiment_counts"],
        "top_topics": news_events_summary["topic_counts"],
        "high_importance_count": news_events_summary["high_importance_count"],
        "importance_counts": news_events_summary["importance_counts"],
        "source_quality_counts": news_events_summary["source_quality_counts"],
        "dominant_topic": news_events_summary["dominant_topic"],
        "dominant_topic_label": news_events_summary["dominant_topic_label"],
        "lookback_days": news_events_summary["lookback_days"],
        "status": news_events_summary["status"],
    }

    return {
        "items": news_events_summary["representative_events"],
        "summary": summary,
    }


def build_display_news_items(news_events_summary: dict) -> list[dict]:
    return [
        {
            "published": (event.get("published_at") or "")[:10],
            "title": event.get("title"),
            "link": event.get("url"),
        }
        for event in news_events_summary.get("representative_events", [])
    ]


def build_agent_summary(news_analysis: dict, news_events_summary: dict) -> dict:
    summary = news_analysis["summary"]

    return {
        "sentiment": summary["sentiment"],
        "total_items": summary["total_items"],
        "top_topics": summary["top_topics"],
        "high_importance_count": summary["high_importance_count"],
        "source": "news_events",
        "lookback_days": news_events_summary["lookback_days"],
    }
