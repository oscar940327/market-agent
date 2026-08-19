import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_providers.price_history import (  # noqa: E402
    build_incremental_price_ingest_plan,
    build_price_ingest_plan,
    fetch_daily_price_history,
    write_price_ingest_report,
)
from data_store.supabase_store import (  # noqa: E402
    fetch_active_tickers,
    fetch_latest_date,
    upsert_daily_prices,
)


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
        "--incremental",
        action="store_true",
        help="Fetch only a short overlap after the latest stored price date.",
    )
    parser.add_argument(
        "--overlap-days",
        type=int,
        default=10,
        help="Calendar-day overlap used by incremental updates.",
    )
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
    print(f"tickers={len(tickers)}")
    print(f"data_end_date={data_end_date}")
    print(f"mode={'incremental' if args.incremental else 'full_history'}")

    results = []
    supabase_status = "skipped"
    supabase_upserted = 0

    for ticker in tickers:
        if args.incremental:
            latest_value = fetch_latest_date(
                table="daily_prices",
                filters={
                    "ticker": f"eq.{ticker}",
                    "provider": "eq.yfinance",
                },
            )
            latest_date = date.fromisoformat(latest_value) if latest_value else None
            plan = build_incremental_price_ingest_plan(
                latest_date=latest_date,
                data_end_date=data_end_date,
                overlap_days=args.overlap_days,
            )
        else:
            latest_value = None
            plan = build_price_ingest_plan(data_end_date=data_end_date)

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
                            f"stored_latest={latest_value or 'missing'}",
                            f"fetch_start={plan.fetch_start_date}",
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
                    f"stored_latest={latest_value or 'missing'}",
                    f"fetch_start={plan.fetch_start_date}",
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
