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

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "news" / "reports"


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
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
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

    output_paths = write_news_summary_report(
        summaries=summaries,
        summary_date=args.summary_date,
        output_dir=Path(args.output_dir),
    )
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")

    return 0


def write_news_summary_report(
    *,
    summaries: list[dict],
    summary_date: str,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "news_summary_accumulation_v1.json"
    markdown_path = output_dir / "news_summary_accumulation_summary_v1.md"
    report = {
        "report_version": "news_summary_accumulation_v1",
        "summary_date": summary_date,
        "ticker_count": len(summaries),
        "total_news_items": sum(int(summary.get("total_events", 0)) for summary in summaries),
        "no_recent_news_count": sum(
            1 for summary in summaries if summary.get("status") == "no_recent_news"
        ),
        "summaries": summaries,
    }
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_news_summary_report_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_news_summary_report_markdown(report: dict) -> str:
    lines = [
        "# News Summary Accumulation",
        "",
        f"- Summary date: `{report['summary_date']}`",
        f"- Tickers summarized: `{report['ticker_count']}`",
        f"- Total news items: `{report['total_news_items']}`",
        f"- No recent news count: `{report['no_recent_news_count']}`",
        "",
        "## Sample Summaries",
        "",
    ]
    for summary in report["summaries"][:10]:
        lines.append(
            "- "
            f"{summary['ticker']}: status={summary['status']}, "
            f"items={summary['total_events']}, "
            f"sentiment={summary['overall_sentiment']}, "
            f"topic={summary['dominant_topic']}"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
