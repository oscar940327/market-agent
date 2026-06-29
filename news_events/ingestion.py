from news_events.normalization import build_news_event_rows
from news_events.providers import fetch_google_news_rss, fetch_yfinance_news


def fetch_and_build_news_events(
    *,
    ticker: str,
    company_name: str | None = None,
    max_items_per_provider: int = 10,
    providers: tuple[str, ...] = ("google_news_rss", "yfinance_news"),
) -> list[dict]:
    raw_items = []

    if "google_news_rss" in providers:
        raw_items.extend(
            fetch_google_news_rss(
                ticker=ticker,
                company_name=company_name,
                max_items=max_items_per_provider,
            )
        )

    if "yfinance_news" in providers:
        raw_items.extend(
            fetch_yfinance_news(
                ticker=ticker,
                max_items=max_items_per_provider,
            )
        )

    return build_news_event_rows(
        ticker=ticker,
        company_name=company_name,
        raw_items=raw_items,
    )
