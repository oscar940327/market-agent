import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_research import build_single_stock_ml_research  # noqa: E402


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "models"
DEFAULT_METRICS_PATH = (
    PROJECT_ROOT / "data" / "ml" / "model_reports" / "baseline_metrics_v1.json"
)
DEFAULT_METADATA_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an ML reference output from the latest dataset row for a ticker.",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--metrics-path", default=str(DEFAULT_METRICS_PATH))
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    args = parser.parse_args()

    output = build_single_stock_ml_research(
        ticker=args.ticker,
        dataset_path=args.dataset_path,
        model_dir=args.model_dir,
        metrics_path=args.metrics_path,
        metadata_path=args.metadata_path,
    )
    print(json.dumps({"ml_research": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
