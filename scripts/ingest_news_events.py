import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import insert_news_events  # noqa: E402
from news_events import fetch_and_build_news_events  # noqa: E402


def parse_tickers(value: str) -> list[str]:
    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch free news sources and write normalized news_events.",
    )
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers.")
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument(
        "--providers",
        default="google_news_rss,yfinance_news",
        help="Comma-separated providers: google_news_rss,yfinance_news.",
    )
    parser.add_argument("--skip-supabase", action="store_true")
    args = parser.parse_args()

    providers = tuple(provider.strip() for provider in args.providers.split(",") if provider.strip())
    all_rows = []

    for ticker in parse_tickers(args.tickers):
        rows = fetch_and_build_news_events(
            ticker=ticker,
            max_items_per_provider=args.max_items,
            providers=providers,
        )
        all_rows.extend(rows)
        print(f"ticker={ticker} news_events={len(rows)}")

    print(f"total_news_events={len(all_rows)}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    result = insert_news_events(all_rows)
    print(f"supabase={result['status']}")
    print(f"inserted={result['inserted_count']}")
    print(f"duplicates={result['duplicate_count']}")

    if result["status"] != "success":
        print(f"message={result.get('message')}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
