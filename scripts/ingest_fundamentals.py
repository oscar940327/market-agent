import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import fetch_active_tickers, upsert_fundamental_snapshots  # noqa: E402
from skills.fundamental_skill import FUNDAMENTAL_FIELDS, get_basic_fundamentals  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch latest basic fundamentals and write fundamental_snapshots.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers for test runs.")
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=100)
    return parser


def resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        tickers = [
            ticker.strip().upper()
            for ticker in args.tickers.split(",")
            if ticker.strip()
        ]
    else:
        tickers = fetch_active_tickers(universe=args.universe)

    if args.limit is not None:
        return tickers[: args.limit]

    return tickers


def build_fundamental_snapshot_record(
    *,
    ticker: str,
    fundamentals: dict,
    provider: str,
    now: datetime,
) -> dict:
    metrics = fundamentals.get("metrics") or {}
    record = {
        "ticker": ticker.upper(),
        "as_of_date": now.date().isoformat(),
        "provider": provider,
        "status": fundamentals.get("status", "success"),
        "summary": fundamentals.get("summary") or {},
        "raw_metrics": metrics,
        "fetched_at": now.isoformat(),
    }
    for field_name in FUNDAMENTAL_FIELDS:
        record[field_name] = metrics.get(field_name)
    return record


def main() -> int:
    args = build_parser().parse_args()
    now = datetime.now(UTC)
    tickers = resolve_tickers(args)
    records = []
    errors = []

    for ticker in tickers:
        try:
            fundamentals = get_basic_fundamentals(ticker)
            record = build_fundamental_snapshot_record(
                ticker=ticker,
                fundamentals=fundamentals,
                provider=args.provider,
                now=now,
            )
            records.append(record)
            print(f"ticker={ticker} fundamentals={fundamentals.get('status')}")
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
            print(f"warning=fundamentals:{ticker}:{exc}")

    print(f"tickers={len(tickers)}")
    print(f"records={len(records)}")
    print(f"errors={len(errors)}")

    if args.skip_supabase:
        print("supabase=skipped")
        print("supabase_upserted=0")
        return 0 if records else 1

    result = upsert_fundamental_snapshots(records, chunk_size=args.chunk_size)
    print(f"supabase={result['status']}")
    print(f"supabase_upserted={result['upserted_count']}")
    if result.get("message"):
        print(f"supabase_message={result['message']}")

    if result["status"] == "error":
        return 1

    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
