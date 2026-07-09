import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import fetch_ml_prediction_outcomes_for_metrics  # noqa: E402
from ml_model_improvement import (  # noqa: E402
    build_step20_calibration_action_report,
    build_step20_calibration_action_summary_markdown,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Step 20 calibration action report from computed outcomes.",
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--model-version")
    parser.add_argument("--bucket-count", type=int, default=10)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outcomes = fetch_ml_prediction_outcomes_for_metrics(
        universe=args.universe,
        model_version=args.model_version,
        days=args.days,
        limit=args.limit,
    )
    report = build_step20_calibration_action_report(
        outcomes,
        days=args.days,
        universe=args.universe,
        model_version=args.model_version,
        bucket_count=args.bucket_count,
    )
    output_paths = write_reports(report, output_dir=Path(args.output_dir))

    print(f"outcomes={len(outcomes)}")
    print(f"computed_outcomes={report['source_calibration_report']['computed_outcomes']}")
    print(f"findings={len(report['findings'])}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    for finding in report["findings"]:
        print(
            f"finding=step20_calibration:{finding['source']}:{finding['target']}:"
            f"{finding['message']}"
        )

    return 0


def write_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "step20_calibration_action_v1.json"
    markdown_path = output_dir / "step20_calibration_action_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_step20_calibration_action_summary_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
