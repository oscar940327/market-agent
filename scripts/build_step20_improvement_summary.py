import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_model_improvement import (  # noqa: E402
    build_step20_improvement_summary_markdown,
    build_step20_improvement_summary_report,
)

DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Step 20 final ML improvement summary.",
    )
    parser.add_argument(
        "--error-analysis-path",
        default=str(DEFAULT_REPORT_DIR / "step20_ml_error_analysis_v1.json"),
    )
    parser.add_argument(
        "--calibration-action-path",
        default=str(DEFAULT_REPORT_DIR / "step20_calibration_action_v1.json"),
    )
    parser.add_argument(
        "--candidate-model-path",
        default=str(DEFAULT_REPORT_DIR / "step20_candidate_model_v2.json"),
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_step20_improvement_summary_report(
        error_analysis=load_json(Path(args.error_analysis_path)),
        calibration_action=load_json(Path(args.calibration_action_path)),
        candidate_model_v2=load_json(Path(args.candidate_model_path)),
    )
    output_paths = write_reports(report, output_dir=Path(args.output_dir))

    print(f"final_status={report['final_recommendation']['status']}")
    print(f"ml_reference_policy={report['decisions']['ml_reference_policy']}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    for action in report["next_actions"]:
        print(f"next_action={action}")
    return 0


def write_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "step20_improvement_summary_v1.json"
    markdown_path = output_dir / "step20_improvement_summary_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_step20_improvement_summary_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
