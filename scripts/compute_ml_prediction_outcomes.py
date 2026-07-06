import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
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

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"
OUTCOME_HORIZONS = {5, 10, 20}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute matured ML prediction outcomes for 5/10/20 trading days.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    predictions = fetch_ml_predictions_for_outcomes(
        universe=args.universe,
        limit=args.limit,
    )
    filtered_predictions = [
        prediction for prediction in predictions if prediction_needs_outcome_update(prediction)
    ]
    skipped_predictions = len(predictions) - len(filtered_predictions)
    print(f"predictions={len(predictions)}")
    print(f"predictions_skipped_completed={skipped_predictions}")
    print(f"predictions_to_update={len(filtered_predictions)}")

    grouped = defaultdict(list)
    for prediction in filtered_predictions:
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
        predictions=filtered_predictions,
        price_rows_by_ticker=price_rows_by_ticker,
    )
    status_counts = count_statuses(updates)
    print(f"updates={len(updates)}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}={count}")
    if status_counts.get("missing_price"):
        print(f"warning=ml_prediction_outcomes:missing_price:{status_counts['missing_price']}")

    report = build_outcome_update_report(
        predictions=predictions,
        filtered_predictions=filtered_predictions,
        skipped_predictions=skipped_predictions,
        updates=updates,
        status_counts=status_counts,
        universe=args.universe,
    )
    output_paths = write_outcome_update_report(
        report,
        output_dir=Path(args.output_dir),
    )
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")

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


def prediction_needs_outcome_update(prediction: dict) -> bool:
    outcomes = prediction.get("ml_prediction_outcomes")
    if not isinstance(outcomes, list):
        return True

    completed_horizons = set()
    for outcome in outcomes:
        horizon = safe_int(outcome.get("horizon_trading_days"))
        if outcome.get("outcome_status") == "computed" and horizon in OUTCOME_HORIZONS:
            completed_horizons.add(horizon)
    return completed_horizons != OUTCOME_HORIZONS


def count_statuses(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("outcome_status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def build_outcome_update_report(
    *,
    predictions: list[dict],
    filtered_predictions: list[dict],
    skipped_predictions: int,
    updates: list[dict],
    status_counts: dict[str, int],
    universe: str,
) -> dict:
    computed_count = status_counts.get("computed", 0)
    pending_count = status_counts.get("pending", 0)
    missing_price_count = status_counts.get("missing_price", 0)
    should_alert = missing_price_count > 0
    return {
        "report_version": "ml_prediction_outcome_update_v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "universe": universe,
        "prediction_count": len(predictions),
        "prediction_count_to_update": len(filtered_predictions),
        "prediction_count_skipped_completed": skipped_predictions,
        "update_count": len(updates),
        "computed_count": computed_count,
        "pending_count": pending_count,
        "missing_price_count": missing_price_count,
        "status_counts": status_counts,
        "alert": {
            "should_alert": should_alert,
            "severity": "warning" if should_alert else "info",
            "reason": "missing_price" if should_alert else "outcomes_recorded",
        },
    }


def write_outcome_update_report(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ml_prediction_outcome_update_v1.json"
    markdown_path = output_dir / "ml_prediction_outcome_update_summary_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_outcome_update_summary_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_outcome_update_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Prediction Outcome Update",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Universe: `{report['universe']}`",
        f"- Predictions fetched: `{report['prediction_count']}`",
        f"- Predictions to update: `{report['prediction_count_to_update']}`",
        f"- Predictions skipped because completed: `{report['prediction_count_skipped_completed']}`",
        f"- Updates built: `{report['update_count']}`",
        f"- Computed outcomes: `{report['computed_count']}`",
        f"- Pending outcomes: `{report['pending_count']}`",
        f"- Missing price outcomes: `{report['missing_price_count']}`",
        "",
        "## Status Counts",
        "",
    ]
    if report["status_counts"]:
        lines.extend(
            f"- `{status}`: `{count}`"
            for status, count in sorted(report["status_counts"].items())
        )
    else:
        lines.append("- No outcome updates were needed.")
    return "\n".join(lines) + "\n"


def safe_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
