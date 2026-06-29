import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_daily_prices,
    fetch_pending_research_outcomes,
    upsert_research_outcomes,
)
from research_logging import build_outcome_updates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute pending 5/10/20 trading-day research outcomes.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--skip-supabase", action="store_true")
    args = parser.parse_args()

    pending = fetch_pending_research_outcomes(limit=args.limit)
    print(f"pending={len(pending)}")

    grouped = defaultdict(list)
    for outcome in pending:
        grouped[(outcome["ticker"], outcome.get("price_provider", "yfinance"))].append(
            outcome
        )

    updates = []
    for (ticker, provider), outcomes in grouped.items():
        price_rows = fetch_daily_prices(ticker=ticker, provider=provider)
        ticker_updates = build_outcome_updates(
            pending_outcomes=outcomes,
            price_data=pd.DataFrame(price_rows),
        )
        updates.extend(ticker_updates)
        print(
            f"ticker={ticker} provider={provider} pending={len(outcomes)} updates={len(ticker_updates)}"
        )

    if args.skip_supabase:
        print("supabase=skipped")
        print(f"updates={len(updates)}")
        return 0

    upsert_result = upsert_research_outcomes(updates)
    print(f"supabase={upsert_result['status']}")
    print(f"supabase_upserted={upsert_result['upserted_count']}")

    if upsert_result["status"] != "success" and updates:
        print(f"message={upsert_result.get('message')}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
