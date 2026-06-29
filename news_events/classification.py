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
    "wins",
    "outperform",
    "optimistic",
]

NEGATIVE_KEYWORDS = [
    "miss",
    "misses",
    "downgrade",
    "cuts",
    "cut",
    "lawsuit",
    "probe",
    "investigation",
    "decline",
    "falls",
    "weak",
    "warning",
    "layoff",
    "risk",
    "underperform",
]

TOPIC_KEYWORDS = {
    "earnings_guidance": [
        "earnings",
        "revenue",
        "profit",
        "eps",
        "quarter",
        "results",
        "guidance",
        "outlook",
        "forecast",
    ],
    "risk_event": [
        "lawsuit",
        "probe",
        "investigation",
        "regulator",
        "recall",
        "warning",
        "risk",
        "tariff",
    ],
    "analyst_rating": [
        "upgrade",
        "downgrade",
        "price target",
        "rating",
        "outperform",
        "underperform",
        "initiates",
    ],
    "product_demand": [
        "demand",
        "supply",
        "inventory",
        "orders",
        "launch",
        "product",
        "chip",
        "server",
        "ai",
        "memory",
    ],
    "short_term_sentiment": [
        "shares rise",
        "shares fall",
        "stock rises",
        "stock falls",
        "rally",
        "selloff",
        "surge",
        "slump",
    ],
    "market_attention": [
        "watch",
        "why",
        "trending",
        "most active",
        "market movers",
    ],
}

HIGH_IMPORTANCE_TOPICS = {"earnings_guidance", "risk_event"}
MEDIUM_IMPORTANCE_TOPICS = {"analyst_rating", "product_demand"}


def classify_news_event(*, title: str, content_snippet: str | None = None) -> dict:
    normalized_text = f"{title} {content_snippet or ''}".lower()
    topic = classify_topic(normalized_text)
    sentiment = classify_sentiment(normalized_text)
    importance = classify_importance(topic=topic, sentiment=sentiment)

    return {
        "sentiment": sentiment,
        "topic": topic,
        "importance": importance,
    }


def classify_topic(normalized_text: str) -> str:
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in normalized_text for keyword in keywords):
            return topic

    return "general"


def classify_sentiment(normalized_text: str) -> str:
    positive_matches = sum(
        1 for keyword in POSITIVE_KEYWORDS if keyword in normalized_text
    )
    negative_matches = sum(
        1 for keyword in NEGATIVE_KEYWORDS if keyword in normalized_text
    )

    if positive_matches > negative_matches:
        return "positive"

    if negative_matches > positive_matches:
        return "negative"

    return "neutral"


def classify_importance(*, topic: str, sentiment: str) -> str:
    if topic in HIGH_IMPORTANCE_TOPICS:
        return "high"

    if topic in MEDIUM_IMPORTANCE_TOPICS:
        return "medium"

    if sentiment != "neutral":
        return "medium"

    return "low"
