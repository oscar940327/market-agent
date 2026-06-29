from pathlib import Path

import pandas as pd

from ml_research.inference import build_ml_research_output
from ml_returns import build_historical_return_reference
from ml_return_model import build_return_model_output


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "models"
DEFAULT_RETURN_MODEL_DIR = PROJECT_ROOT / "data" / "ml" / "return_models"
DEFAULT_METRICS_PATH = (
    PROJECT_ROOT / "data" / "ml" / "model_reports" / "baseline_metrics_v1.json"
)
DEFAULT_RETURN_METRICS_PATH = (
    PROJECT_ROOT / "data" / "ml" / "return_model_reports" / "return_model_metrics_v1.json"
)
DEFAULT_METADATA_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"


def build_single_stock_ml_research(
    *,
    ticker: str,
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    metrics_path: str | Path = DEFAULT_METRICS_PATH,
    return_model_dir: str | Path = DEFAULT_RETURN_MODEL_DIR,
    return_metrics_path: str | Path = DEFAULT_RETURN_METRICS_PATH,
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
) -> dict:
    try:
        dataset = load_training_dataset(dataset_path=dataset_path)
        latest_row = select_latest_feature_row(ticker=ticker, dataset=dataset)
        return_reference = build_historical_return_reference(
            feature_row=latest_row,
            dataset=dataset,
        )
        return_model = build_optional_return_model_output(
            feature_row=latest_row,
            return_model_dir=return_model_dir,
            return_metrics_path=return_metrics_path,
        )
        return build_ml_research_output(
            feature_row=latest_row,
            model_dir=model_dir,
            metrics_path=metrics_path,
            dataset_metadata_path=metadata_path,
            return_reference=return_reference,
            return_model=return_model,
        )
    except FileNotFoundError as error:
        return build_unavailable_ml_research(
            reason="missing_ml_artifacts",
            message=str(error),
        )
    except LookupError as error:
        return build_unavailable_ml_research(
            reason="dataset_row_not_found",
            message=str(error),
        )
    except Exception as error:
        return build_unavailable_ml_research(
            reason="ml_reference_error",
            message=str(error),
        )


def load_latest_feature_row(*, ticker: str, dataset_path: str | Path) -> dict:
    dataset = load_training_dataset(dataset_path=dataset_path)
    return select_latest_feature_row(ticker=ticker, dataset=dataset)


def load_training_dataset(*, dataset_path: str | Path) -> pd.DataFrame:
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Training dataset not found: {dataset_path}")

    return pd.read_csv(dataset_path)


def select_latest_feature_row(*, ticker: str, dataset: pd.DataFrame) -> dict:
    if "ticker" not in dataset.columns or "date" not in dataset.columns:
        raise LookupError("Training dataset is missing ticker/date columns.")

    rows = dataset[dataset["ticker"].str.upper() == ticker.upper()].copy()
    if rows.empty:
        raise LookupError(f"No training dataset rows found for ticker={ticker.upper()}.")

    return rows.sort_values("date").iloc[-1].to_dict()


def build_unavailable_ml_research(*, reason: str, message: str) -> dict:
    return {
        "status": "unavailable",
        "usage_policy": "reference_only",
        "reason": reason,
        "message": message,
        "summary": f"ML reference is currently unavailable. Reason: {reason}.",
    }


def build_optional_return_model_output(
    *,
    feature_row: dict,
    return_model_dir: str | Path,
    return_metrics_path: str | Path,
) -> dict:
    try:
        return build_return_model_output(
            feature_row=feature_row,
            model_dir=return_model_dir,
            metrics_path=return_metrics_path,
        )
    except FileNotFoundError as error:
        return {
            "status": "unavailable",
            "usage_policy": "experimental_reference_only",
            "reason": "return_model_artifacts_missing",
            "message": str(error),
            "summary": "Return model is unavailable. Historical return reference remains the primary range reference.",
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "usage_policy": "experimental_reference_only",
            "reason": "return_model_error",
            "message": str(error),
            "summary": "Return model is unavailable. Historical return reference remains the primary range reference.",
        }
