import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_active_tickers,
    fetch_news_events,
    upsert_news_event_summaries,
)
from news_events import build_news_summary  # noqa: E402


def parse_tickers(value: str | None) -> list[str]:
    if not value:
        return []

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def build_news_summary_record(
    *,
    summary: dict,
    summary_date: str,
    provider: str,
    generated_at: str,
) -> dict:
    return {
        "ticker": summary["ticker"].upper(),
        "summary_date": summary_date,
        "window_days": int(summary["lookback_days"]),
        "total_items": int(summary["total_events"]),
        "overall_sentiment": summary["overall_sentiment"],
        "dominant_topic": summary["dominant_topic"],
        "dominant_topic_label": summary.get("dominant_topic_label"),
        "high_importance_count": int(summary["high_importance_count"]),
        "summary_json": summary,
        "provider": provider,
        "generated_at": generated_at,
        "updated_at": generated_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a 30-day news summary from Supabase news_events.",
    )
    parser.add_argument("--ticker", help="Single ticker. Kept for quick checks.")
    parser.add_argument("--tickers", help="Comma-separated tickers.")
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--provider", default="market_agent")
    parser.add_argument("--summary-date", default=date.today().isoformat())
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=100)
    args = parser.parse_args()

    tickers = parse_tickers(args.tickers)
    if args.ticker:
        tickers.append(args.ticker.upper())
    if not tickers:
        tickers = fetch_active_tickers(universe=args.universe)

    generated_at = datetime.now(UTC).isoformat()
    summaries = []
    records = []

    for ticker in tickers:
        rows = fetch_news_events(ticker=ticker, limit=args.limit)
        summary = build_news_summary(
            ticker=ticker,
            news_events=rows,
            lookback_days=args.lookback_days,
        )
        summaries.append(summary)
        records.append(
            build_news_summary_record(
                summary=summary,
                summary_date=args.summary_date,
                provider=args.provider,
                generated_at=generated_at,
            )
        )
        print(
            f"ticker={ticker} status={summary['status']} "
            f"total_events={summary['total_events']}"
        )

    if args.skip_supabase:
        print("supabase=skipped")
    else:
        result = upsert_news_event_summaries(
            records,
            chunk_size=args.chunk_size,
        )
        print(f"supabase={result['status']}")
        print(f"supabase_upserted={result['upserted_count']}")
        if result["status"] != "success":
            print(f"supabase_message={result.get('message')}")
            return 1

    if args.ticker and not args.tickers:
        print(json.dumps(summaries[0], ensure_ascii=False, indent=2))
    else:
        print(f"summaries={len(summaries)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
