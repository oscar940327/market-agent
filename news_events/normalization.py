import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from news_events.extractor import classify_news_event_with_optional_llm


COMPANY_ALIASES = {
    "AAPL": ["apple"],
    "AMD": ["advanced micro devices", "amd"],
    "AMZN": ["amazon"],
    "GOOG": ["alphabet", "google"],
    "GOOGL": ["alphabet", "google"],
    "META": ["meta", "facebook"],
    "MSFT": ["microsoft"],
    "MU": ["micron"],
    "NVDA": ["nvidia"],
    "TSLA": ["tesla"],
}


def build_news_event_rows(
    *,
    ticker: str,
    raw_items: list[dict],
    company_name: str | None = None,
) -> list[dict]:
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows = []

    for item in raw_items:
        title = clean_text(item.get("title", ""))
        if not title:
            continue

        url = normalize_url(item.get("url", ""))
        snippet = clean_text(item.get("content_snippet", ""))
        published_at = item.get("published_at")
        duplicate_group_id = build_duplicate_group_id(
            ticker=ticker,
            title=title,
            published_at=published_at,
        )
        confidence = classify_ticker_mapping_confidence(
            ticker=ticker,
            title=title,
            snippet=snippet,
            provider=item.get("provider"),
            company_name=company_name,
        )
        classification = classify_news_event_with_optional_llm(
            ticker=ticker,
            title=title,
            content_snippet=snippet,
            mode="rule_based",
        )
        extractor = classification["extractor"]

        rows.append(
            {
                "ticker": ticker.upper(),
                "source": item.get("source") or "unknown",
                "source_type": item.get("source_type") or "unknown",
                "title": title,
                "content_snippet": snippet or None,
                "url": url or None,
                "published_at": published_at,
                "fetched_at": fetched_at,
                "sentiment": classification["sentiment"],
                "topic": classification["topic"],
                "importance": classification["importance"],
                "extractor_mode": extractor["mode_used"],
                "extractor_provider": extractor.get("provider"),
                "extractor_model": extractor.get("model"),
                "extraction_status": "success",
                "llm_summary": classification.get("summary"),
                "ticker_relevance": classification.get("ticker_relevance"),
                "extraction_error": extractor.get("message"),
                "source_quality": classify_source_quality(
                    source=item.get("source") or "",
                    source_type=item.get("source_type") or "",
                ),
                "duplicate_group_id": duplicate_group_id,
                "ticker_mapping_confidence": confidence,
            }
        )

    return rows


def build_duplicate_group_id(
    *,
    ticker: str,
    title: str,
    published_at: str | None,
) -> str:
    normalized_title = normalize_title(title)
    published_date = (published_at or "")[:10]
    raw_key = f"{ticker.upper()}|{published_date}|{normalized_title}"
    return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:16]


def classify_ticker_mapping_confidence(
    *,
    ticker: str,
    title: str,
    snippet: str,
    provider: str | None = None,
    company_name: str | None = None,
) -> str:
    if provider in {"google_news_rss", "yfinance_news"}:
        return "high"

    haystack = f"{title} {snippet}".lower()
    aliases = [ticker.lower(), *(COMPANY_ALIASES.get(ticker.upper(), []))]
    if company_name:
        aliases.append(company_name.lower())

    if any(alias in haystack for alias in aliases):
        return "medium"

    return "low"


def classify_source_quality(*, source: str, source_type: str) -> str:
    normalized_source = source.lower()

    if source_type in {"company_ir", "sec_filing", "earnings_transcript"}:
        return "high"

    high_sources = ["reuters", "associated press", "sec", "investor relations"]
    medium_sources = [
        "yahoo finance",
        "cnbc",
        "marketwatch",
        "barron's",
        "investopedia",
        "the motley fool",
        "zacks",
        "seeking alpha",
    ]

    if any(source_name in normalized_source for source_name in high_sources):
        return "high"

    if source_type in {"finance_news", "news_aggregator"}:
        return "medium"

    if any(source_name in normalized_source for source_name in medium_sources):
        return "medium"

    return "unknown"


def normalize_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    if parsed.netloc == "news.google.com" and parsed.path.startswith("/rss/articles/"):
        return url

    query = parse_qs(parsed.query)
    if "url" in query and query["url"]:
        return query["url"][0]

    return url


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return " ".join(title.split())


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()
