CLASSIFICATION_MODEL_VERSION = "baseline_v1"
RETURN_MODEL_VERSION = "return_baseline_v1"
FEATURE_VERSION = "ml_features_v1"
LABEL_VERSION = "ml_labels_v1"
DATASET_VERSION = "training_dataset_v1"
DAILY_PREDICTION_VERSION = "daily_prediction_v1"
MARKET_SNAPSHOT_VERSION = "market_snapshot_v1"


def build_versioning_payload() -> dict:
    return {
        "classification_model_version": CLASSIFICATION_MODEL_VERSION,
        "return_model_version": RETURN_MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "dataset_version": DATASET_VERSION,
        "daily_prediction_version": DAILY_PREDICTION_VERSION,
        "market_snapshot_version": MARKET_SNAPSHOT_VERSION,
    }
