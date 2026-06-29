import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_providers.price_history import (  # noqa: E402
    build_price_ingest_plan,
    fetch_daily_price_history,
    write_price_ingest_report,
)
from data_store.supabase_store import fetch_active_tickers, upsert_daily_prices  # noqa: E402


def parse_tickers(value: str | None) -> list[str] | None:
    if not value:
        return None

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 15 years plus 2 months of daily OHLCV prices.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers, e.g. MU,NVDA,AAPL.")
    parser.add_argument("--limit", type=int, help="Limit active universe tickers.")
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--data-end-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument(
        "--output-dir",
        default="data/market/prices",
        help="Directory for ingest reports.",
    )
    parser.add_argument(
        "--skip-supabase",
        action="store_true",
        help="Fetch and report only. Do not write prices to Supabase.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Supabase daily_prices upsert chunk size.",
    )
    args = parser.parse_args()

    tickers = parse_tickers(args.tickers)
    if tickers is None:
        tickers = fetch_active_tickers(universe=args.universe)

    if args.limit:
        tickers = tickers[: args.limit]

    data_end_date = (
        date.fromisoformat(args.data_end_date) if args.data_end_date else date.today()
    )
    plan = build_price_ingest_plan(data_end_date=data_end_date)

    print(f"tickers={len(tickers)}")
    print(f"data_end_date={plan.data_end_date}")
    print(f"research_start_date={plan.research_start_date}")
    print(f"fetch_start_date={plan.fetch_start_date}")

    results = []
    supabase_status = "skipped"
    supabase_upserted = 0

    for ticker in tickers:
        result = fetch_daily_price_history(ticker=ticker, plan=plan)
        results.append(result)

        if not args.skip_supabase and result.records:
            upsert_result = upsert_daily_prices(
                result.records,
                chunk_size=args.chunk_size,
            )
            supabase_status = upsert_result["status"]
            supabase_upserted += upsert_result["upserted_count"]
            if upsert_result["status"] != "success":
                print(
                    " ".join(
                        [
                            f"ticker={result.ticker}",
                            f"supabase={upsert_result['status']}",
                            f"message={upsert_result.get('message')}",
                        ]
                    )
                )
                return 1

        print(
            " ".join(
                [
                    f"ticker={result.ticker}",
                    f"status={result.status}",
                    f"provider={result.provider}",
                    f"rows={result.row_count}",
                    f"supabase_rows={len(result.records) if not args.skip_supabase else 0}",
                ]
            )
        )

    report_path, missing_path = write_price_ingest_report(
        results=results,
        output_dir=args.output_dir,
    )
    print(f"report={report_path}")
    print(f"missing_price_data={missing_path}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    print(f"supabase={supabase_status}")
    print(f"supabase_upserted={supabase_upserted}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
