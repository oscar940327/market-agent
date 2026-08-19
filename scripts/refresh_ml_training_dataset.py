import argparse
import csv
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
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
    upsert_ml_dataset_metadata,
)
from ml_dataset import build_training_dataset, write_dataset_outputs  # noqa: E402
from ml_dataset.builder import build_metadata  # noqa: E402


DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_METADATA_PATH = (
    PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the recent labeled rows in an existing weekly ML dataset."
    )
    parser.add_argument("--window-days", type=int, default=240)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--technical-version", default="v1")
    parser.add_argument("--market-benchmark", default="QQQ")
    parser.add_argument("--market-rule-version", default="v1")
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH))
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print("status=failed")
        print("message=Weekly ML dataset artifact is missing; run weekly-ml-dataset first.")
        return 1

    start_date = (date.today() - timedelta(days=args.window_days)).isoformat()
    tickers = fetch_active_tickers(universe=args.universe)
    market_regime_rows = fetch_market_regimes(
        benchmark=args.market_benchmark,
        rule_version=args.market_rule_version,
        start_date=start_date,
    )

    daily_price_rows_by_ticker = {}
    technical_rows_by_ticker = {}
    news_event_rows_by_ticker = {}
    similar_case_rows_by_ticker = {}
    for ticker in tickers:
        daily_price_rows_by_ticker[ticker] = fetch_daily_prices(
            ticker=ticker,
            provider=args.provider,
            start_date=start_date,
        )
        technical_rows_by_ticker[ticker] = fetch_technical_features(
            ticker=ticker,
            price_provider=args.provider,
            feature_version=args.technical_version,
            start_date=start_date,
        )
        news_event_rows_by_ticker[ticker] = fetch_news_events_for_dataset(
            ticker=ticker,
            start_date=start_date,
        )
        similar_case_rows_by_ticker[ticker] = fetch_similar_case_results(
            ticker=ticker,
            start_date=start_date,
        )
        print(
            f"ticker={ticker} prices={len(daily_price_rows_by_ticker[ticker])} "
            f"technicals={len(technical_rows_by_ticker[ticker])} "
            f"news={len(news_event_rows_by_ticker[ticker])} "
            f"similar_cases={len(similar_case_rows_by_ticker[ticker])}"
        )

    recent_result = build_training_dataset(
        tickers=tickers,
        daily_price_rows_by_ticker=daily_price_rows_by_ticker,
        technical_rows_by_ticker=technical_rows_by_ticker,
        market_regime_rows=market_regime_rows,
        news_event_rows_by_ticker=news_event_rows_by_ticker,
        similar_case_rows_by_ticker=similar_case_rows_by_ticker,
        universe=args.universe,
    )
    existing_rows = load_csv_rows(csv_path)
    merged_rows = merge_rows(existing_rows, recent_result["rows"])
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    metadata = build_metadata(
        rows=merged_rows,
        universe=args.universe,
        feature_version=recent_result["metadata"]["feature_version"],
        label_version=recent_result["metadata"]["label_version"],
        generated_at=generated_at,
        excluded_reasons=Counter(
            recent_result["metadata"].get("excluded_row_reason_summary") or {}
        ),
    )
    metadata["refresh_mode"] = "weekly_base_plus_recent_window"
    metadata["refresh_window_start"] = start_date
    metadata["base_row_count"] = len(existing_rows)
    metadata["recent_row_count"] = len(recent_result["rows"])

    write_dataset_outputs(
        rows=merged_rows,
        metadata=metadata,
        csv_path=csv_path,
        metadata_path=args.metadata_path,
    )
    metadata_result = upsert_ml_dataset_metadata(
        {
            "dataset_name": "training_dataset_v1",
            "dataset_version": "training_dataset_v1",
            "universe": args.universe,
            "provider": args.provider,
            "feature_version": metadata["feature_version"],
            "label_version": metadata["label_version"],
            "generated_at": generated_at,
            "data_start_date": metadata.get("data_start_date"),
            "data_end_date": metadata.get("data_end_date"),
            "row_count": metadata["row_count"],
            "status": "success",
            "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
            "metadata": metadata,
        }
    )

    print("status=success")
    print(f"window_start={start_date}")
    print(f"base_rows={len(existing_rows)}")
    print(f"recent_rows={len(recent_result['rows'])}")
    print(f"merged_rows={len(merged_rows)}")
    print(f"data_end_date={metadata.get('data_end_date')}")
    print(f"metadata_sync={metadata_result['status']}")
    if metadata_result.get("message"):
        print(f"message={metadata_result['message']}")
    return 0 if metadata_result["status"] == "success" else 1


def load_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def merge_rows(existing_rows: list[dict], recent_rows: list[dict]) -> list[dict]:
    merged = {
        (str(row.get("ticker", "")).upper(), str(row.get("date", ""))): row
        for row in existing_rows
    }
    for row in recent_rows:
        merged[(row["ticker"].upper(), row["date"])] = row
    return sorted(merged.values(), key=lambda row: (row["ticker"], row["date"]))


if __name__ == "__main__":
    raise SystemExit(main())
