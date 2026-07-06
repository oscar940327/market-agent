import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_model_improvement import (  # noqa: E402
    build_model_comparison_report,
    build_model_comparison_summary_markdown,
)


DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Step 15 model comparison and promotion review.",
    )
    parser.add_argument(
        "--baseline-audit-path",
        default=str(DEFAULT_REPORT_DIR / "step15_baseline_audit_v1.json"),
    )
    parser.add_argument(
        "--candidate-experiment-path",
        default=str(DEFAULT_REPORT_DIR / "step15_candidate_model_experiment_v1.json"),
    )
    parser.add_argument(
        "--diagnostics-path",
        default=str(DEFAULT_REPORT_DIR / "step15_feature_label_diagnostics_v1.json"),
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_model_comparison_report(
        baseline_audit=load_json(args.baseline_audit_path),
        candidate_experiment=load_json(args.candidate_experiment_path),
        diagnostics_report=load_optional_json(args.diagnostics_path),
    )
    output_paths = write_comparison_report(report, output_dir=Path(args.output_dir))
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    print(f"final_status={report['final_recommendation']['status']}")
    print(f"ml_reference_policy={report['final_recommendation']['ml_reference_policy']}")
    print(f"promotion_recommendation={report['promotion_policy']['recommendation']}")
    return 0


def write_comparison_report(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "step15_model_comparison_v1.json"
    markdown_path = output_dir / "step15_model_comparison_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_model_comparison_summary_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_optional_json(path: str | None) -> dict | None:
    if not path:
        return None
    report_path = Path(path)
    if not report_path.exists():
        return None
    return load_json(str(report_path))


if __name__ == "__main__":
    raise SystemExit(main())
