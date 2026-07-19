import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_dataset import FEATURE_COLUMNS  # noqa: E402
from ml_model_improvement import (  # noqa: E402
    build_step28_quality_upgrade,
    build_step28_summary_markdown,
    reevaluate_step28_report,
)
from ml_model_improvement.quality_upgrade import (  # noqa: E402
    CLASSIFICATION_TARGETS,
    REGRESSION_TARGETS,
)


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Step 28 walk-forward model quality and promotion report."
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--classification-models",
        default="logistic_regression,random_forest,extra_trees,xgboost,lightgbm",
    )
    parser.add_argument(
        "--regression-models",
        default="random_forest,hist_gradient_boosting,xgboost,lightgbm",
    )
    parser.add_argument("--max-train-rows", type=int, default=60_000)
    parser.add_argument("--max-evaluation-rows", type=int, default=40_000)
    parser.add_argument(
        "--reevaluate-existing",
        action="store_true",
        help="Reapply the current quality policy to an existing report without retraining models.",
    )
    args = parser.parse_args(argv)

    existing_path = Path(args.output_dir) / "step28_model_quality_upgrade_v1.json"
    if args.reevaluate_existing:
        if not existing_path.exists():
            raise FileNotFoundError(f"Step 28 report not found: {existing_path}")
        report = reevaluate_step28_report(
            json.loads(existing_path.read_text(encoding="utf-8"))
        )
        paths = write_reports(report, output_dir=Path(args.output_dir))
        print(f"promotion_status={report['promotion']['status']}")
        print(f"json_path={paths['json_path']}")
        print(f"markdown_path={paths['markdown_path']}")
        return 0

    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"ML dataset not found: {dataset_path}")
    dataset = read_evaluation_dataset(dataset_path)
    report = build_step28_quality_upgrade(
        dataset,
        classification_models=parse_list(args.classification_models),
        regression_models=parse_list(args.regression_models),
        max_train_rows=args.max_train_rows,
        max_evaluation_rows=args.max_evaluation_rows,
    )
    paths = write_reports(report, output_dir=Path(args.output_dir))

    print(f"dataset_rows={report['dataset']['rows']}")
    print(f"folds={len(report['evaluation_design']['folds'])}")
    for target, result in report["targets"].items():
        print(
            f"target={target} candidate={result.get('best_candidate')} "
            f"quality={(result.get('quality') or {}).get('level')} "
            f"promotion={result.get('promotion_decision')}"
        )
    print(f"promotion_status={report['promotion']['status']}")
    print(f"json_path={paths['json_path']}")
    print(f"markdown_path={paths['markdown_path']}")
    return 0


def read_evaluation_dataset(path: Path) -> pd.DataFrame:
    available = set(pd.read_csv(path, nrows=0).columns)
    required = {
        "ticker",
        "date",
        "market_regime",
        *FEATURE_COLUMNS,
        *CLASSIFICATION_TARGETS,
        *REGRESSION_TARGETS,
    }
    usecols = sorted(required & available)
    return pd.read_csv(path, usecols=usecols, low_memory=False)


def write_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "step28_model_quality_upgrade_v1.json"
    markdown_path = output_dir / "step28_model_quality_upgrade_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(build_step28_summary_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
