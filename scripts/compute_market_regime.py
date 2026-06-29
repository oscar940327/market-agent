import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import fetch_daily_prices, upsert_market_regimes  # noqa: E402
from market_regime import build_market_regime_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute benchmark market regimes.")
    parser.add_argument("--benchmark", default="QQQ")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--skip-supabase", action="store_true")
    args = parser.parse_args()

    rows = fetch_daily_prices(ticker=args.benchmark, provider=args.provider)
    records = build_market_regime_records(
        benchmark=args.benchmark,
        price_data=pd.DataFrame(rows),
    )
    print(f"benchmark={args.benchmark}")
    print(f"price_rows={len(rows)}")
    print(f"regime_rows={len(records)}")

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
