from collections import Counter
from datetime import UTC, datetime, timedelta


TOPIC_LABELS = {
    "earnings_guidance": "影響財報預期",
    "risk_event": "有風險消息",
    "analyst_rating": "分析師看法改變",
    "product_demand": "有產品或需求題材",
    "short_term_sentiment": "影響短線情緒",
    "market_attention": "只是市場在關注",
    "general": "一般新聞",
}


def build_news_summary(
    *,
    ticker: str,
    news_events: list[dict],
    lookback_days: int = 30,
    now: datetime | None = None,
) -> dict:
    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(days=lookback_days)
    recent_events = [
        event
        for event in news_events
        if is_recent(event.get("published_at"), cutoff=cutoff)
    ]

    if not recent_events:
        return {
            "ticker": ticker.upper(),
            "status": "no_recent_news",
            "lookback_days": lookback_days,
            "total_events": 0,
            "sentiment_counts": {},
            "topic_counts": {},
            "importance_counts": {},
            "source_quality_counts": {},
            "overall_sentiment": "unknown",
            "dominant_topic": None,
            "dominant_topic_label": None,
            "high_importance_count": 0,
            "representative_events": [],
        }

    sentiment_counts = count_field(recent_events, "sentiment")
    topic_counts = count_field(recent_events, "topic")
    importance_counts = count_field(recent_events, "importance")
    source_quality_counts = count_field(recent_events, "source_quality")
    dominant_topic = most_common_key(topic_counts)

    return {
        "ticker": ticker.upper(),
        "status": "success",
        "lookback_days": lookback_days,
        "total_events": len(recent_events),
        "sentiment_counts": sentiment_counts,
        "topic_counts": topic_counts,
        "importance_counts": importance_counts,
        "source_quality_counts": source_quality_counts,
        "overall_sentiment": determine_overall_sentiment(sentiment_counts),
        "dominant_topic": dominant_topic,
        "dominant_topic_label": TOPIC_LABELS.get(dominant_topic),
        "high_importance_count": importance_counts.get("high", 0),
        "representative_events": select_representative_events(recent_events),
    }


def is_recent(published_at: str | None, *, cutoff: datetime) -> bool:
    if not published_at:
        return False

    parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed >= cutoff


def count_field(events: list[dict], field: str) -> dict:
    return dict(Counter(event.get(field) or "unknown" for event in events))


def most_common_key(counts: dict) -> str | None:
    if not counts:
        return None

    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def determine_overall_sentiment(sentiment_counts: dict) -> str:
    positive = sentiment_counts.get("positive", 0)
    negative = sentiment_counts.get("negative", 0)

    if positive > negative:
        return "positive"

    if negative > positive:
        return "negative"

    return "neutral"


def select_representative_events(events: list[dict], limit: int = 3) -> list[dict]:
    importance_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    quality_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3}

    sorted_events = sorted(
        events,
        key=lambda event: (
            importance_rank.get(event.get("importance"), 3),
            quality_rank.get(event.get("source_quality"), 3),
            event.get("published_at") or "",
        ),
    )

    return [
        {
            "title": event.get("title"),
            "source": event.get("source"),
            "published_at": event.get("published_at"),
            "sentiment": event.get("sentiment"),
            "topic": event.get("topic"),
            "importance": event.get("importance"),
            "source_quality": event.get("source_quality"),
            "url": event.get("url"),
        }
        for event in sorted_events[:limit]
    ]
