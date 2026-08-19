import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_daily_prices,
    fetch_latest_date,
    upsert_market_regimes,
)
from market_regime import build_market_regime_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute benchmark market regimes.")
    parser.add_argument("--benchmark", default="QQQ")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--rule-version", default="v1")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--overlap-days", type=int, default=10)
    parser.add_argument("--skip-supabase", action="store_true")
    args = parser.parse_args()

    latest_value = None
    price_start_date = None
    if args.incremental:
        latest_value = fetch_latest_date(
            table="market_regimes",
            filters={
                "benchmark": f"eq.{args.benchmark.upper()}",
                "rule_version": f"eq.{args.rule_version}",
            },
        )
        if latest_value:
            price_start_date = (
                date.fromisoformat(latest_value) - timedelta(days=args.warmup_days)
            ).isoformat()

    rows = fetch_daily_prices(
        ticker=args.benchmark,
        provider=args.provider,
        start_date=price_start_date,
    )
    records = build_market_regime_records(
        benchmark=args.benchmark,
        price_data=pd.DataFrame(rows),
        rule_version=args.rule_version,
    )
    if args.incremental and latest_value:
        affected_start = (
            date.fromisoformat(latest_value) - timedelta(days=args.overlap_days)
        ).isoformat()
        records = [record for record in records if record["date"] >= affected_start]
    print(f"benchmark={args.benchmark}")
    print(f"price_rows={len(rows)}")
    print(f"regime_rows={len(records)}")
    print(f"stored_latest={latest_value or 'missing'}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    upsert_result = upsert_market_regimes(records, chunk_size=1000)
    print(f"supabase={upsert_result['status']}")
    print(f"supabase_upserted={upsert_result['upserted_count']}")

    if upsert_result["status"] != "success":
        print(f"supabase_message={upsert_result.get('message')}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
