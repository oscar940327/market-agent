import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_active_tickers,
    fetch_daily_prices,
    upsert_technical_features,
)
from technical_features import build_technical_feature_records  # noqa: E402


def parse_tickers(value: str | None) -> list[str] | None:
    if not value:
        return None

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute daily technical features from Supabase daily_prices.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers, e.g. MU,NVDA,AAPL.")
    parser.add_argument("--limit", type=int, help="Limit active universe tickers.")
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument(
        "--skip-supabase",
        action="store_true",
        help="Compute only. Do not write technical_features to Supabase.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Supabase technical_features upsert chunk size.",
    )
    args = parser.parse_args()

    tickers = parse_tickers(args.tickers)
    if tickers is None:
        tickers = fetch_active_tickers(universe=args.universe)

    if args.limit:
        tickers = tickers[: args.limit]

    print(f"tickers={len(tickers)}")
    print(f"provider={args.provider}")

    total_features = 0
    total_upserted = 0

    for ticker in tickers:
        rows = fetch_daily_prices(ticker=ticker, provider=args.provider)
        price_data = pd.DataFrame(rows)
        records = build_technical_feature_records(
            ticker=ticker,
            price_provider=args.provider,
            price_data=price_data,
        )
        total_features += len(records)

        if args.skip_supabase:
            print(
                f"ticker={ticker} price_rows={len(rows)} feature_rows={len(records)} supabase_rows=0"
            )
            continue

        upsert_result = upsert_technical_features(
            records,
            chunk_size=args.chunk_size,
        )
        if upsert_result["status"] not in {"success", "skipped"}:
            print(
                f"ticker={ticker} supabase={upsert_result['status']} "
                f"message={upsert_result.get('message')}"
            )
            return 1

        total_upserted += upsert_result["upserted_count"]
        print(
            f"ticker={ticker} price_rows={len(rows)} feature_rows={len(records)} "
            f"supabase_rows={upsert_result['upserted_count']}"
        )

    print(f"features={total_features}")
    print(f"supabase={'skipped' if args.skip_supabase else 'success'}")
    print(f"supabase_upserted={total_upserted}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
