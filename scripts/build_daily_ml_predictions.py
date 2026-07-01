import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from daily_ml_predictions import (  # noqa: E402
    build_failed_prediction_record,
    build_ml_model_run_row,
    build_prediction_record,
    select_ticker_metadata,
)
from data_freshness import build_current_data_freshness  # noqa: E402
from data_store import (  # noqa: E402
    fetch_active_ticker_metadata,
    insert_ml_model_run,
    upsert_ml_predictions,
)
from ml_research import build_single_stock_ml_research  # noqa: E402
from ml_research.service import load_latest_feature_row  # noqa: E402


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "models"
DEFAULT_RETURN_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "return_models"
DEFAULT_METRICS_PATH = (
    PROJECT_ROOT / "data" / "ml" / "model_reports" / "baseline_metrics_v1.json"
)
DEFAULT_RETURN_METRICS_PATH = (
    PROJECT_ROOT / "data" / "ml" / "return_model_reports" / "return_model_metrics_v1.json"
)
DEFAULT_METADATA_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"


def parse_tickers(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def apply_limit(tickers: list[str], limit: int | None) -> list[str]:
    if limit is None:
        return tickers
    return tickers[:limit]


def resolve_tickers_and_metadata(
    *,
    universe: str,
    tickers: list[str] | None,
    limit: int | None,
) -> tuple[list[str], dict[str, dict]]:
    rows = fetch_active_ticker_metadata(universe=universe)
    if tickers:
        selected_tickers = apply_limit(tickers, limit)
    else:
        selected_tickers = apply_limit(
            [row["ticker"].upper() for row in rows if row.get("ticker")],
            limit,
        )
    return selected_tickers, select_ticker_metadata(rows, selected_tickers)


def build_records_for_tickers(
    *,
    tickers: list[str],
    ticker_metadata: dict[str, dict],
    model_run_id: str,
    universe: str,
    provider: str,
    retry_per_ticker: int,
    dataset_path: str | Path,
    model_dir: str | Path,
    metrics_path: str | Path,
    return_model_dir: str | Path,
    return_metrics_path: str | Path,
    metadata_path: str | Path,
    skip_freshness: bool = False,
) -> tuple[list[dict], list[dict]]:
    records = []
    failures = []
    for ticker in tickers:
        attempts = retry_per_ticker + 1
        for attempt in range(1, attempts + 1):
            try:
                record = build_record_for_ticker(
                    ticker=ticker,
                    ticker_metadata=ticker_metadata.get(ticker, {"ticker": ticker}),
                    model_run_id=model_run_id,
                    universe=universe,
                    provider=provider,
                    dataset_path=dataset_path,
                    model_dir=model_dir,
                    metrics_path=metrics_path,
                    return_model_dir=return_model_dir,
                    return_metrics_path=return_metrics_path,
                    metadata_path=metadata_path,
                    skip_freshness=skip_freshness,
                )
                records.append(record)
                break
            except Exception as error:
                if attempt < attempts:
                    continue
                failure = {
                    "ticker": ticker,
                    "attempts": attempt,
                    "error": str(error),
                }
                failures.append(failure)
                records.append(
                    build_failed_prediction_record(
                        ticker=ticker,
                        model_run_id=model_run_id,
                        error_message=str(error),
                        ticker_metadata=ticker_metadata.get(ticker, {"ticker": ticker}),
                        universe=universe,
                        price_provider=provider,
                    )
                )
    return records, failures


def build_record_for_ticker(
    *,
    ticker: str,
    ticker_metadata: dict,
    model_run_id: str,
    universe: str,
    provider: str,
    dataset_path: str | Path,
    model_dir: str | Path,
    metrics_path: str | Path,
    return_model_dir: str | Path,
    return_metrics_path: str | Path,
    metadata_path: str | Path,
    skip_freshness: bool,
) -> dict:
    feature_row = load_latest_feature_row(ticker=ticker, dataset_path=dataset_path)
    ml_research = build_single_stock_ml_research(
        ticker=ticker,
        dataset_path=dataset_path,
        model_dir=model_dir,
        metrics_path=metrics_path,
        return_model_dir=return_model_dir,
        return_metrics_path=return_metrics_path,
        metadata_path=metadata_path,
    )
    data_freshness = (
        {"overall": "unknown", "warnings": []}
        if skip_freshness
        else build_current_data_freshness(ticker=ticker, provider=provider)
    )
    return build_prediction_record(
        ticker=ticker,
        model_run_id=model_run_id,
        ml_research=ml_research,
        feature_row=feature_row,
        ticker_metadata=ticker_metadata,
        data_freshness=data_freshness,
        universe=universe,
        price_provider=provider,
    )


def infer_data_as_of(dataset_path: str | Path, metadata_path: str | Path) -> str:
    metadata = load_json(metadata_path)
    if metadata.get("data_end_date"):
        return str(metadata["data_end_date"])[:10]

    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        return datetime.now(UTC).date().isoformat()
    frame = pd.read_csv(dataset_path, usecols=["date"])
    if frame.empty:
        return datetime.now(UTC).date().isoformat()
    return str(frame["date"].max())[:10]


def load_json(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build daily ML predictions and market snapshots for active universe tickers.",
    )
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--tickers", help="Comma-separated tickers for a small test run.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-freshness", action="store_true")
    parser.add_argument("--retry-per-ticker", type=int, default=1)
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--metrics-path", default=str(DEFAULT_METRICS_PATH))
    parser.add_argument("--return-model-dir", default=str(DEFAULT_RETURN_MODEL_DIR))
    parser.add_argument("--return-metrics-path", default=str(DEFAULT_RETURN_METRICS_PATH))
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    parser.add_argument("--pipeline-run-id")
    args = parser.parse_args()

    requested_tickers = parse_tickers(args.tickers)
    tickers, ticker_metadata = resolve_tickers_and_metadata(
        universe=args.universe,
        tickers=requested_tickers,
        limit=args.limit,
    )
    data_as_of = infer_data_as_of(args.dataset_path, args.metadata_path)
    started_at = datetime.now(UTC)
    run_row = build_ml_model_run_row(
        data_as_of=data_as_of,
        universe=args.universe,
        provider=args.provider,
        pipeline_run_id=args.pipeline_run_id,
        started_at=started_at,
        status="completed",
        config={
            "tickers": tickers,
            "limit": args.limit,
            "retry_per_ticker": args.retry_per_ticker,
            "skip_freshness": args.skip_freshness,
        },
    )

    if args.dry_run:
        model_run_id = "00000000-0000-0000-0000-000000000000"
    else:
        run_result = insert_ml_model_run(run_row)
        if run_result["status"] != "success":
            print(f"model_run=error")
            print(f"message={run_result.get('message')}")
            return 1
        model_run_id = run_result["row"]["id"]

    records, failures = build_records_for_tickers(
        tickers=tickers,
        ticker_metadata=ticker_metadata,
        model_run_id=model_run_id,
        universe=args.universe,
        provider=args.provider,
        retry_per_ticker=args.retry_per_ticker,
        dataset_path=args.dataset_path,
        model_dir=args.model_dir,
        metrics_path=args.metrics_path,
        return_model_dir=args.return_model_dir,
        return_metrics_path=args.return_metrics_path,
        metadata_path=args.metadata_path,
        skip_freshness=args.skip_freshness,
    )

    if args.dry_run:
        upsert_result = {"status": "skipped", "upserted_count": 0}
    else:
        upsert_result = upsert_ml_predictions(records)

    status = "success"
    if failures:
        status = "partial_success"
    if upsert_result["status"] == "error":
        status = "failed"

    print(f"status={status}")
    print(f"tickers={len(tickers)}")
    print(f"records={len(records)}")
    print(f"failures={len(failures)}")
    print(f"model_run_id={model_run_id}")
    print(f"supabase={upsert_result['status']}")
    print(f"upserted={upsert_result.get('upserted_count', 0)}")
    if failures:
        print(f"failed_tickers={','.join(failure['ticker'] for failure in failures)}")
    if args.dry_run and records:
        print(json.dumps({"sample_record": records[0]}, ensure_ascii=False, indent=2))

    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
