import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_return_model import (  # noqa: E402
    run_boosting_return_experiment,
    write_boosting_experiment_outputs,
)


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "return_model_reports"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Step 7.8C XGBoost / LightGBM return model experiment.",
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--sample-rows", type=int)
    parser.add_argument("--max-train-rows", type=int, default=120000)
    args = parser.parse_args()

    dataset = pd.read_csv(args.dataset_path)
    if args.sample_rows and len(dataset) > args.sample_rows:
        dataset = sample_dataset_by_split(dataset, args.sample_rows)

    result = run_boosting_return_experiment(
        dataset,
        max_train_rows=args.max_train_rows,
    )
    output_paths = write_boosting_experiment_outputs(
        result=result,
        report_dir=args.report_dir,
    )
    print(f"dataset_rows={len(dataset)}")
    print(f"available_models={','.join(result['available_models']) or 'none'}")
    print(f"skipped_models={result['skipped_models']}")
    print(f"metrics_path={output_paths['metrics_path']}")
    print(f"summary_path={output_paths['summary_path']}")
    for target, target_result in result["targets"].items():
        model_names = ",".join(target_result.get("models", {})) or "none"
        print(
            f"target={target} status={target_result['status']} "
            f"models={model_names}",
        )
    return 0


def sample_dataset_by_split(dataset: pd.DataFrame, sample_rows: int) -> pd.DataFrame:
    if sample_rows <= 0:
        return dataset

    split_order = ["train", "validation", "test"]
    per_split = max(1, sample_rows // len(split_order))
    frames = []
    for split in split_order:
        split_frame = dataset[dataset["split"] == split].sort_values(["date", "ticker"])
        if split_frame.empty:
            continue
        frames.append(split_frame.tail(min(per_split, len(split_frame))))
    sampled = pd.concat(frames, ignore_index=True)
    return sampled.sort_values(["date", "ticker"]).reset_index(drop=True)


if __name__ == "__main__":
    raise SystemExit(main())
