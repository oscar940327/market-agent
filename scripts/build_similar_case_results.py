import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import fetch_active_ticker_metadata, upsert_similar_case_results  # noqa: E402
from similar_cases import build_similar_case_result_rows  # noqa: E402


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and persist daily similar-case results from the ML training dataset.",
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument(
        "--all-dates",
        action="store_true",
        help="Backfill every dataset row. Default only builds latest row per ticker.",
    )
    parser.add_argument("--limit", type=int, help="Limit query rows for manual runs.")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        print(f"status=failed")
        print(f"message=dataset_not_found:{dataset_path}")
        return 1

    metadata = fetch_active_ticker_metadata(universe=args.universe)
    result = build_similar_case_result_rows(
        dataset_path=dataset_path,
        ticker_metadata=metadata,
        universe=args.universe,
        latest_per_ticker=not args.all_dates,
        max_queries=args.limit,
        min_samples=args.min_samples,
    )
    output_paths = write_accumulation_report(result, output_dir=Path(args.output_dir))

    print(f"status={result['status']}")
    print(f"dataset_rows={result['dataset_rows']}")
    print(f"result_count={result['result_count']}")
    print(f"fresh_count={result['fresh_count']}")
    print(f"missing_count={result['missing_count']}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    if result["missing_count"]:
        print(f"warning=similar_case_results:missing:{result['missing_count']}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    upsert_result = upsert_similar_case_results(
        result["result_rows"],
        chunk_size=args.chunk_size,
    )
    print(f"supabase={upsert_result['status']}")
    print(f"supabase_upserted={upsert_result['upserted_count']}")
    if upsert_result["status"] != "success":
        print(f"message={upsert_result.get('message')}")
        return 1
    return 0


def write_accumulation_report(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "similar_case_accumulation_v1.json"
    markdown_path = output_dir / "similar_case_accumulation_summary_v1.md"
    serializable = {**report, "result_rows": report["result_rows"][:20]}
    json_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_accumulation_summary_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_accumulation_summary_markdown(report: dict) -> str:
    lines = [
        "# Similar Case Accumulation",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Dataset rows: `{report['dataset_rows']}`",
        f"- Result rows: `{report['result_count']}`",
        f"- Fresh results: `{report['fresh_count']}`",
        f"- Missing results: `{report['missing_count']}`",
        "",
        "## Sample Results",
        "",
    ]
    if not report["result_rows"]:
        lines.append("- No similar-case results were generated.")
    else:
        for row in report["result_rows"][:10]:
            lines.append(
                "- "
                f"{row['query_ticker']} {row['query_date']}: "
                f"{row['scope']} / {row['relaxation_step']} / "
                f"sample={row['sample_size']} / evidence={row['evidence_quality']}"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
