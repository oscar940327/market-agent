import argparse
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import (  # noqa: E402
    fetch_daily_prices,
    fetch_ml_predictions_for_outcomes,
    upsert_ml_prediction_outcomes,
)
from ml_prediction_outcomes import build_ml_prediction_outcome_updates  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute matured ML prediction outcomes for 5/10/20 trading days.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--skip-supabase", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    predictions = fetch_ml_predictions_for_outcomes(
        universe=args.universe,
        limit=args.limit,
    )
    print(f"predictions={len(predictions)}")

    grouped = defaultdict(list)
    for prediction in predictions:
        grouped[
            (
                prediction["ticker"].upper(),
                prediction.get("price_provider") or "yfinance",
            )
        ].append(prediction)

    price_rows_by_ticker = {}
    for ticker, provider in grouped:
        rows = fetch_daily_prices(ticker=ticker, provider=provider)
        price_rows_by_ticker[(ticker, provider)] = rows
        print(f"ticker={ticker} provider={provider} prices={len(rows)} predictions={len(grouped[(ticker, provider)])}")

    updates = build_ml_prediction_outcome_updates(
        predictions=predictions,
        price_rows_by_ticker=price_rows_by_ticker,
    )
    status_counts = count_statuses(updates)
    print(f"updates={len(updates)}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}={count}")
    if status_counts.get("missing_price"):
        print(f"warning=ml_prediction_outcomes:missing_price:{status_counts['missing_price']}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    upsert_result = upsert_ml_prediction_outcomes(updates)
    print(f"supabase={upsert_result['status']}")
    print(f"supabase_upserted={upsert_result['upserted_count']}")

    if upsert_result["status"] != "success" and updates:
        print(f"warning=ml_prediction_outcomes:supabase_error:{upsert_result.get('message')}")
        print(f"message={upsert_result.get('message')}")
        return 1

    return 0


def count_statuses(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("outcome_status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
