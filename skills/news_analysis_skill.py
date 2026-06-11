POSITIVE_KEYWORDS = [
    "beat",
    "beats",
    "upgrade",
    "raises",
    "raised",
    "growth",
    "record",
    "surge",
    "strong",
    "partnership",
    "expands",
]

NEGATIVE_KEYWORDS = [
    "miss",
    "misses",
    "downgrade",
    "cuts",
    "cut",
    "lawsuit",
    "probe",
    "decline",
    "falls",
    "weak",
    "warning",
    "layoff",
    "risk",
]

TOPIC_KEYWORDS = {
    "earnings": ["earnings", "revenue", "profit", "eps", "quarter", "results"],
    "guidance": ["guidance", "outlook", "forecast", "raises", "cuts"],
    "industry_demand": ["demand", "supply", "inventory", "cycle", "orders"],
    "product": ["launch", "product", "chip", "server", "ai", "memory"],
    "analyst_rating": ["upgrade", "downgrade", "price target", "rating"],
    "lawsuit": ["lawsuit", "probe", "investigation", "regulator"],
    "macro": ["fed", "inflation", "rates", "tariff", "policy"],
}

HIGH_IMPORTANCE_TOPICS = {
    "earnings",
    "guidance",
    "lawsuit",
    "industry_demand",
}


def analyze_news_items(news_items: list[dict]) -> dict:
    analyzed_items = [analyze_news_item(item) for item in news_items]
    sentiment_counts = count_by_key(analyzed_items, "sentiment")
    topic_counts = count_by_key(analyzed_items, "topic")

    return {
        "items": analyzed_items,
        "summary": {
            "total_items": len(analyzed_items),
            "sentiment": determine_overall_sentiment(sentiment_counts),
            "sentiment_counts": sentiment_counts,
            "top_topics": topic_counts,
            "high_importance_count": len(
                [item for item in analyzed_items if item["importance"] == "high"]
            ),
        },
    }


def analyze_news_item(news_item: dict) -> dict:
    title = news_item.get("title", "")
    normalized_title = title.lower()
    topic = classify_topic(normalized_title)
    sentiment = classify_sentiment(normalized_title)
    importance = classify_importance(topic=topic, sentiment=sentiment)

    return {
        **news_item,
        "topic": topic,
        "sentiment": sentiment,
        "importance": importance,
    }


def classify_topic(normalized_title: str) -> str:
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in normalized_title for keyword in keywords):
            return topic

    return "general"


def classify_sentiment(normalized_title: str) -> str:
    positive_matches = sum(
        1 for keyword in POSITIVE_KEYWORDS if keyword in normalized_title
    )
    negative_matches = sum(
        1 for keyword in NEGATIVE_KEYWORDS if keyword in normalized_title
    )

    if positive_matches > negative_matches:
        return "positive"

    if negative_matches > positive_matches:
        return "negative"

    return "neutral"


def classify_importance(topic: str, sentiment: str) -> str:
    if topic in HIGH_IMPORTANCE_TOPICS:
        return "high"

    if sentiment != "neutral":
        return "medium"

    return "low"


def count_by_key(items: list[dict], key: str) -> dict:
    counts = {}

    for item in items:
        value = item[key]
        counts[value] = counts.get(value, 0) + 1

    return counts


def determine_overall_sentiment(sentiment_counts: dict) -> str:
    positive = sentiment_counts.get("positive", 0)
    negative = sentiment_counts.get("negative", 0)

    if positive > negative:
        return "positive"

    if negative > positive:
        return "negative"

    return "neutral"
