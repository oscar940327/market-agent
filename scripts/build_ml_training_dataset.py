import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_active_tickers,
    fetch_daily_prices,
    fetch_market_regimes,
    fetch_news_events_for_dataset,
    fetch_similar_case_results,
    fetch_technical_features,
)
from ml_dataset import build_training_dataset, write_dataset_outputs  # noqa: E402


DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_METADATA_PATH = (
    PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"
)


def parse_tickers(value: str | None) -> list[str] | None:
    if not value:
        return None

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build local ML training dataset CSV from Supabase market data.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers, e.g. MU,NVDA,AAPL.")
    parser.add_argument("--limit", type=int, help="Limit active universe tickers.")
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--technical-version", default="v1")
    parser.add_argument("--market-benchmark", default="QQQ")
    parser.add_argument("--market-rule-version", default="v1")
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH))
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    args = parser.parse_args()

    tickers = parse_tickers(args.tickers)
    if tickers is None:
        tickers = fetch_active_tickers(universe=args.universe)

    if args.limit:
        tickers = tickers[: args.limit]

    print(f"tickers={len(tickers)}")
    print(f"universe={args.universe}")
    print(f"provider={args.provider}")

    market_regime_rows = fetch_market_regimes(
        benchmark=args.market_benchmark,
        rule_version=args.market_rule_version,
    )
    print(f"market_regime_rows={len(market_regime_rows)}")

    daily_price_rows_by_ticker = {}
    technical_rows_by_ticker = {}
    news_event_rows_by_ticker = {}
    similar_case_rows_by_ticker = {}

    for ticker in tickers:
        daily_price_rows_by_ticker[ticker] = fetch_daily_prices(
            ticker=ticker,
            provider=args.provider,
        )
        technical_rows_by_ticker[ticker] = fetch_technical_features(
            ticker=ticker,
            price_provider=args.provider,
            feature_version=args.technical_version,
        )
        news_event_rows_by_ticker[ticker] = fetch_news_events_for_dataset(
            ticker=ticker,
        )
        similar_case_rows_by_ticker[ticker] = fetch_similar_case_results(
            ticker=ticker,
        )
        print(
            f"ticker={ticker} "
            f"prices={len(daily_price_rows_by_ticker[ticker])} "
            f"technicals={len(technical_rows_by_ticker[ticker])} "
            f"news={len(news_event_rows_by_ticker[ticker])} "
            f"similar_cases={len(similar_case_rows_by_ticker[ticker])}"
        )

    result = build_training_dataset(
        tickers=tickers,
        daily_price_rows_by_ticker=daily_price_rows_by_ticker,
        technical_rows_by_ticker=technical_rows_by_ticker,
        market_regime_rows=market_regime_rows,
        news_event_rows_by_ticker=news_event_rows_by_ticker,
        similar_case_rows_by_ticker=similar_case_rows_by_ticker,
        universe=args.universe,
    )
    write_dataset_outputs(
        rows=result["rows"],
        metadata=result["metadata"],
        csv_path=args.csv_path,
        metadata_path=args.metadata_path,
    )

    metadata = result["metadata"]
    print(f"dataset_rows={metadata['row_count']}")
    print(f"train_count={metadata['train_count']}")
    print(f"validation_count={metadata['validation_count']}")
    print(f"test_count={metadata['test_count']}")
    print(f"csv_path={args.csv_path}")
    print(f"metadata_path={args.metadata_path}")
    print(f"excluded={metadata['excluded_row_reason_summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
