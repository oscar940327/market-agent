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
)
from data_store.supabase_store import (  # noqa: E402
    fetch_latest_date,
    upsert_daily_prices,
    upsert_tickers,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update QQQ benchmark prices.")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--overlap-days", type=int, default=10)
    args = parser.parse_args()

    benchmark = "QQQ"
    upsert_ticker_result = upsert_tickers(
        [
            {
                "ticker": benchmark,
                "name": "Invesco QQQ Trust",
                "industry": "Benchmark ETF",
                "themes": ["benchmark"],
                "market_cap_bucket": None,
                "volatility_bucket": None,
                "universe": "BENCHMARK",
                "universe_provider": "manual_benchmark",
                "is_active": True,
                "first_seen_at": date.today().isoformat(),
                "last_seen_at": date.today().isoformat(),
                "updated_at": date.today().isoformat(),
            }
        ]
    )
    print(f"ticker_upsert={upsert_ticker_result['status']}")
    print(f"ticker_upserted={upsert_ticker_result['upserted_count']}")

    latest_value = None
    if args.incremental:
        latest_value = fetch_latest_date(
            table="daily_prices",
            filters={"ticker": "eq.QQQ", "provider": "eq.yfinance"},
        )
        plan = build_incremental_price_ingest_plan(
            latest_date=date.fromisoformat(latest_value) if latest_value else None,
            overlap_days=args.overlap_days,
        )
    else:
        plan = build_price_ingest_plan()
    result = fetch_daily_price_history(ticker=benchmark, plan=plan)
    print(f"ticker={benchmark}")
    print(f"status={result.status}")
    print(f"provider={result.provider}")
    print(f"mode={'incremental' if args.incremental else 'full_history'}")
    print(f"stored_latest={latest_value or 'missing'}")
    print(f"fetch_start={plan.fetch_start_date}")
    print(f"rows={result.row_count}")

    upsert_price_result = upsert_daily_prices(result.records, chunk_size=1000)
    print(f"daily_prices={upsert_price_result['status']}")
    print(f"daily_prices_upserted={upsert_price_result['upserted_count']}")

    if upsert_ticker_result["status"] != "success":
        print(f"ticker_message={upsert_ticker_result.get('message')}")
        return 1

    if upsert_price_result["status"] != "success":
        print(f"daily_prices_message={upsert_price_result.get('message')}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
