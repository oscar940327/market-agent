import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_model_improvement import (  # noqa: E402
    build_candidate_model_experiment,
    build_candidate_model_experiment_summary_markdown,
)

DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Step 20 candidate model v2 experiment.",
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--targets",
        default="up_5d,up_10d,up_20d,large_drop_20d",
    )
    parser.add_argument(
        "--models",
        default="logistic_regression,random_forest,xgboost,lightgbm",
    )
    parser.add_argument("--max-train-rows", type=int, default=120000)
    parser.add_argument("--sample-rows", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = pd.read_csv(args.dataset_path)
    if args.sample_rows and len(dataset) > args.sample_rows:
        dataset = dataset.sort_values(["date", "ticker"]).head(args.sample_rows)

    report = build_candidate_model_experiment(
        dataset,
        targets=parse_csv_arg(args.targets),
        model_names=parse_csv_arg(args.models),
        max_train_rows=args.max_train_rows,
    )
    report = convert_to_step20_report(report)
    output_paths = write_candidate_reports(report, output_dir=Path(args.output_dir))

    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    for target, target_result in report["targets"].items():
        print(
            f"target={target} status={target_result.get('status')} "
            f"best_model={target_result.get('best_model')}"
        )
        readiness = target_result.get("promotion_readiness") or {}
        if readiness:
            print(f"promotion_readiness={target}:{readiness.get('status')}")
    for recommendation in report["recommendations"]:
        print(f"recommendation={recommendation}")
    return 0


def convert_to_step20_report(report: dict) -> dict:
    converted = dict(report)
    converted["report_version"] = "step20_candidate_model_v2"
    converted["step20_context"] = {
        "purpose": "candidate_model_v2_static_comparison",
        "uses_existing_step15_trainer": True,
        "promotion_policy": "do_not_promote_without_monitoring_calibration_and_downside_review",
    }
    converted["recommendations"] = [
        *report.get("recommendations", []),
        "Step 20 candidate v2 must be reviewed with error analysis, calibration action, and downside overlay before promotion.",
    ]
    return converted


def write_candidate_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "step20_candidate_model_v2.json"
    markdown_path = output_dir / "step20_candidate_model_v2.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown = build_candidate_model_experiment_summary_markdown(report).replace(
        "# Step 15 Candidate Model Experiment",
        "# Step 20 Candidate Model v2 Experiment",
        1,
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def parse_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
