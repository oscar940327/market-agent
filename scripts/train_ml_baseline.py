import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_baseline import train_baseline_models, write_baseline_outputs  # noqa: E402


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "models"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train Step 7.5 baseline ML models from training_dataset_v1.csv.",
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument(
        "--sample-rows",
        type=int,
        help="Optional deterministic sample size for quick local smoke tests.",
    )
    args = parser.parse_args()

    dataset = pd.read_csv(args.dataset_path)
    if args.sample_rows and len(dataset) > args.sample_rows:
        dataset = dataset.sort_values(["date", "ticker"]).head(args.sample_rows)

    result = train_baseline_models(dataset)
    output_paths = write_baseline_outputs(
        result=result,
        report_dir=args.report_dir,
        model_dir=args.model_dir,
    )

    print(f"dataset_rows={len(dataset)}")
    print(f"metrics_path={output_paths['metrics_path']}")
    print(f"feature_importance_path={output_paths['feature_importance_path']}")
    print(f"summary_path={output_paths['summary_path']}")
    print(f"model_files={len(output_paths['model_paths'])}")
    for target, target_result in result["targets"].items():
        print(f"target={target} status={target_result['status']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
