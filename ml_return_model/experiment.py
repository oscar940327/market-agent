import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from ml_return_model.trainer import (
    RETURN_MODEL_TARGETS,
    build_feature_matrices,
    directional_accuracy,
    downside_underestimation_rate,
    evaluate_point_model,
    evaluate_quantile_models,
    extract_feature_importance,
    limit_training_rows,
)


EXPERIMENT_VERSION = "return_boosting_experiment_v1"


def run_boosting_return_experiment(
    dataset: pd.DataFrame,
    *,
    targets: list[str] | None = None,
    random_state: int = 42,
    max_train_rows: int = 120000,
) -> dict:
    targets = targets or RETURN_MODEL_TARGETS
    optional_models = build_optional_model_factories(random_state=random_state)
    result = {
        "experiment_version": EXPERIMENT_VERSION,
        "status": "success",
        "usage_policy": "comparison_only",
        "targets": {},
        "available_models": sorted(optional_models),
        "skipped_models": build_skipped_models(optional_models),
    }

    split_frames = {
        split: dataset[dataset["split"] == split].copy()
        for split in ["train", "validation", "test"]
    }
    matrices = build_feature_matrices(split_frames)

    for target in targets:
        if target not in dataset.columns:
            result["targets"][target] = {
                "status": "skipped",
                "reason": "missing_target_column",
            }
            continue

        target_frames = {
            split: frame.dropna(subset=[target]).copy()
            for split, frame in split_frames.items()
        }
        if target_frames["train"].empty or target_frames["validation"].empty:
            result["targets"][target] = {
                "status": "skipped",
                "reason": "missing_train_or_validation_split",
            }
            continue

        train_frame = limit_training_rows(
            target_frames["train"],
            max_rows=max_train_rows,
            random_state=random_state,
        )
        x_train = matrices["train"].loc[train_frame.index]
        y_train = pd.to_numeric(train_frame[target], errors="coerce")

        model_results = {}
        for model_name, factory in optional_models.items():
            started_at = perf_counter()
            point_model = factory["point"]()
            point_model.fit(x_train, y_train)
            point_result = evaluate_point_model(
                target=target,
                model=point_model,
                matrices=matrices,
                split_frames=target_frames,
            )
            point_result["training_seconds"] = round(perf_counter() - started_at, 3)
            point_result["feature_importance"] = extract_feature_importance(
                point_model,
                matrices["train"].columns,
            )
            model_results[model_name] = {"point_model": point_result}

            if factory.get("q25") and factory.get("q75"):
                range_started_at = perf_counter()
                low_model = factory["q25"]()
                high_model = factory["q75"]()
                low_model.fit(x_train, y_train)
                high_model.fit(x_train, y_train)
                range_result = evaluate_quantile_models(
                    target=target,
                    low_model=low_model,
                    high_model=high_model,
                    matrices=matrices,
                    split_frames=target_frames,
                )
                range_result["training_seconds"] = round(
                    perf_counter() - range_started_at,
                    3,
                )
                model_results[model_name]["range_model"] = range_result

        result["targets"][target] = {
            "status": "success" if model_results else "skipped",
            "reason": None if model_results else "no_optional_models_available",
            "row_counts": {split: len(frame) for split, frame in target_frames.items()},
            "training_row_count_used": int(len(train_frame)),
            "models": model_results,
        }

    return result


def build_optional_model_factories(*, random_state: int) -> dict:
    factories = {}

    try:
        from xgboost import XGBRegressor

        factories["xgboost"] = {
            "point": lambda: XGBRegressor(
                objective="reg:squarederror",
                n_estimators=160,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_weight=20,
                reg_lambda=1.0,
                random_state=random_state,
                n_jobs=1,
            ),
        }
    except ImportError:
        pass

    try:
        from lightgbm import LGBMRegressor

        factories["lightgbm"] = {
            "point": lambda: LGBMRegressor(
                objective="regression",
                n_estimators=180,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_samples=80,
                reg_lambda=1.0,
                random_state=random_state,
                n_jobs=1,
                verbosity=-1,
            ),
            "q25": lambda: LGBMRegressor(
                objective="quantile",
                alpha=0.25,
                n_estimators=180,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_samples=80,
                reg_lambda=1.0,
                random_state=random_state,
                n_jobs=1,
                verbosity=-1,
            ),
            "q75": lambda: LGBMRegressor(
                objective="quantile",
                alpha=0.75,
                n_estimators=180,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_samples=80,
                reg_lambda=1.0,
                random_state=random_state,
                n_jobs=1,
                verbosity=-1,
            ),
        }
    except ImportError:
        pass

    return factories


def build_skipped_models(optional_models: dict) -> dict:
    skipped = {}
    if "xgboost" not in optional_models:
        skipped["xgboost"] = "package_not_installed"
    if "lightgbm" not in optional_models:
        skipped["lightgbm"] = "package_not_installed"
    return skipped


def write_boosting_experiment_outputs(
    *,
    result: dict,
    report_dir: str | Path,
) -> dict:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = report_dir / "return_boosting_experiment_metrics_v1.json"
    summary_path = report_dir / "return_boosting_experiment_summary_v1.md"
    metrics_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(build_experiment_summary_markdown(result), encoding="utf-8")
    return {
        "metrics_path": str(metrics_path),
        "summary_path": str(summary_path),
    }


def build_experiment_summary_markdown(result: dict) -> str:
    lines = [
        "# Return Boosting Experiment Summary",
        "",
        f"- Experiment version: `{result['experiment_version']}`",
        "- Usage: comparison only. This does not replace the active return model.",
        f"- Available models: {', '.join(result.get('available_models') or ['none'])}",
        "",
    ]

    skipped_models = result.get("skipped_models") or {}
    if skipped_models:
        lines.append("## Skipped Models")
        for model_name, reason in skipped_models.items():
            lines.append(f"- {model_name}: {reason}")
        lines.append("")

    for target, target_result in result.get("targets", {}).items():
        lines.append(f"## {target}")
        if target_result.get("status") != "success":
            lines.append(f"- Status: {target_result.get('status')}")
            lines.append(f"- Reason: {target_result.get('reason')}")
            lines.append("")
            continue

        for model_name, model_result in target_result.get("models", {}).items():
            point_metrics = (
                model_result.get("point_model", {})
                .get("metrics", {})
                .get("test", {})
            )
            lines.append(f"### {model_name}")
            lines.append(f"- Test MAE: {format_metric(point_metrics.get('mae'))}")
            lines.append(f"- Test RMSE: {format_metric(point_metrics.get('rmse'))}")
            lines.append(
                "- Test directional accuracy: "
                f"{format_metric(point_metrics.get('directional_accuracy'))}"
            )
            range_metrics = (
                model_result.get("range_model", {})
                .get("metrics", {})
                .get("test", {})
            )
            if range_metrics:
                lines.append(
                    "- Test interval coverage: "
                    f"{format_metric(range_metrics.get('coverage'))}"
                )
            lines.append("")

    lines.append("These experiment results are not trading advice.")
    lines.append("")
    return "\n".join(lines)


def format_metric(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
