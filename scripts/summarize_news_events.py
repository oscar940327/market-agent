import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import fetch_news_events  # noqa: E402
from news_events import build_news_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a 30-day news summary from Supabase news_events.",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    rows = fetch_news_events(ticker=args.ticker, limit=args.limit)
    summary = build_news_summary(
        ticker=args.ticker,
        news_events=rows,
        lookback_days=args.lookback_days,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
