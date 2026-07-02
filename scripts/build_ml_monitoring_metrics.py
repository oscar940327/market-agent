import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import fetch_ml_prediction_outcomes_for_metrics  # noqa: E402
from ml_monitoring import (  # noqa: E402
    build_monitoring_metrics_report,
    build_monitoring_summary_markdown,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ML monitoring metrics report.")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--model-version")
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
    report = build_monitoring_metrics_report(
        outcomes,
        days=args.days,
        universe=args.universe,
        model_version=args.model_version,
    )
    output_paths = write_monitoring_reports(report, output_dir=Path(args.output_dir))

    print(f"outcomes={len(outcomes)}")
    print(f"computed_outcomes={report['computed_outcomes']}")
    print(f"warnings={len(report['warnings'])}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    for warning in report["warnings"]:
        print(
            f"warning=ml_monitoring:{warning['metric']}:"
            f"{warning['message']}"
        )

    return 0


def write_monitoring_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = build_report_suffix(report)
    json_path = output_dir / f"ml_metrics_report_{suffix}.json"
    markdown_path = output_dir / f"ml_metrics_summary_{suffix}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_monitoring_summary_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_report_suffix(report: dict) -> str:
    model = report.get("model_version") or "all_models"
    return f"{model}_{report['window_days']}d_v1"


if __name__ == "__main__":
    raise SystemExit(main())
