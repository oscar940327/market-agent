import email.utils
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


GOOGLE_NEWS_RSS_URL = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=en-US&gl=US&ceid=US:en"
)


def fetch_google_news_rss(
    *,
    ticker: str,
    company_name: str | None = None,
    max_items: int = 10,
    open_url=urlopen,
) -> list[dict]:
    query = build_google_news_query(ticker=ticker, company_name=company_name)
    url = GOOGLE_NEWS_RSS_URL.format(query=quote_plus(query))
    request = Request(
        url,
        headers={
            "User-Agent": "market-agent/0.1 news-provider",
            "Accept": "application/rss+xml, application/xml",
        },
    )

    with open_url(request, timeout=30) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    items = []

    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", default="")
        source_element = item.find("source")
        source = (
            source_element.text.strip()
            if source_element is not None and source_element.text
            else "Google News"
        )
        items.append(
            {
                "provider": "google_news_rss",
                "source": source,
                "source_type": "news_aggregator",
                "title": title.strip(),
                "content_snippet": item.findtext("description", default="").strip(),
                "url": item.findtext("link", default="").strip(),
                "published_at": parse_rss_datetime(
                    item.findtext("pubDate", default="")
                ),
            }
        )

    return items


def fetch_yfinance_news(
    *,
    ticker: str,
    max_items: int = 10,
) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return []

    stock = yf.Ticker(ticker)
    raw_items = stock.news or []
    items = []

    for raw_item in raw_items[:max_items]:
        content = raw_item.get("content") if isinstance(raw_item, dict) else None
        item = content or raw_item
        title = item.get("title", "")
        url = item.get("canonicalUrl", {}).get("url") or item.get("link") or item.get("url")
        provider = item.get("provider", {}) if isinstance(item.get("provider"), dict) else {}
        published = item.get("pubDate") or item.get("displayTime") or item.get("providerPublishTime")

        items.append(
            {
                "provider": "yfinance_news",
                "source": provider.get("displayName") or item.get("publisher") or "Yahoo Finance",
                "source_type": "finance_news",
                "title": title.strip(),
                "content_snippet": (item.get("summary") or "").strip(),
                "url": url or "",
                "published_at": parse_yfinance_datetime(published),
            }
        )

    return items


def build_google_news_query(*, ticker: str, company_name: str | None = None) -> str:
    if company_name:
        return f'({ticker} OR "{company_name}") stock'

    return f"{ticker} stock"


def parse_rss_datetime(value: str) -> str | None:
    if not value:
        return None

    parsed = email.utils.parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_yfinance_datetime(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).replace(microsecond=0).isoformat()

    if isinstance(value, str):
        if "T" in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC).replace(microsecond=0).isoformat()

        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat()

    return None
