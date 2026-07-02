import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_freshness import build_current_data_freshness  # noqa: E402
from ml_monitoring import (  # noqa: E402
    build_drift_report_from_csv,
    build_drift_summary_markdown,
)

DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ML dataset drift report.")
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--recent-days", type=int, default=30)
    parser.add_argument("--baseline-days", type=int, default=365)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--skip-freshness", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    freshness_report = None if args.skip_freshness else safe_build_freshness_report()
    report = build_drift_report_from_csv(
        args.dataset_path,
        recent_days=args.recent_days,
        baseline_days=args.baseline_days,
        freshness_report=freshness_report,
    )
    output_paths = write_drift_reports(report, output_dir=Path(args.output_dir))

    print(f"dataset_rows={report['dataset_rows']}")
    print(f"recent_rows={report['recent_rows']}")
    print(f"baseline_rows={report['baseline_rows']}")
    print(f"warnings={len(report['warnings'])}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    for warning in report["warnings"]:
        print(
            f"warning=ml_drift:{warning['metric']}:"
            f"{warning['message']}"
        )

    return 0


def safe_build_freshness_report() -> dict:
    try:
        return build_current_data_freshness(ticker="QQQ")
    except Exception as exc:
        return {
            "overall": "unknown",
            "warnings": [
                {
                    "source": "data_freshness",
                    "status": "warning",
                    "message": f"Freshness check failed: {exc}",
                }
            ],
        }


def write_drift_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{report['recent_days']}d_vs_{report['baseline_days']}d_v1"
    json_path = output_dir / f"ml_drift_report_{suffix}.json"
    markdown_path = output_dir / f"ml_drift_summary_{suffix}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_drift_summary_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
