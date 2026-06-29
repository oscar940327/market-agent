import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_providers.price_history import build_price_ingest_plan, fetch_daily_price_history  # noqa: E402
from data_store.supabase_store import upsert_daily_prices, upsert_tickers  # noqa: E402


def main() -> int:
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

    plan = build_price_ingest_plan()
    result = fetch_daily_price_history(ticker=benchmark, plan=plan)
    print(f"ticker={benchmark}")
    print(f"status={result.status}")
    print(f"provider={result.provider}")
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
