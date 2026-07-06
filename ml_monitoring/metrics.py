from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any


HORIZONS = (5, 10, 20)
DEFAULT_WARNING_THRESHOLDS = {
    "min_sample_size": 50,
    "min_up_accuracy": 0.50,
    "max_downside_underestimation_rate": 0.20,
}
DEFAULT_CALIBRATION_THRESHOLDS = {
    "min_usable_sample_size": 50,
    "max_mean_absolute_calibration_error": 0.10,
    "max_calibration_error": 0.20,
}


def build_monitoring_metrics_report(
    outcomes: list[dict],
    *,
    days: int = 90,
    universe: str = "QQQ100",
    model_version: str | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_WARNING_THRESHOLDS, **(thresholds or {})}
    computed = [row for row in outcomes if row.get("outcome_status") == "computed"]
    generated = generated_at or datetime.now(UTC)
    horizon_metrics = {
        str(horizon): build_horizon_metrics(computed, horizon=horizon)
        for horizon in HORIZONS
    }
    warnings = build_warnings(horizon_metrics, thresholds=thresholds)
    data_status = "no_computed_outcomes" if not computed else "ready"
    return {
        "report_version": "ml_monitoring_metrics_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "window_days": days,
        "universe": universe,
        "model_version": model_version,
        "data_status": data_status,
        "thresholds": thresholds,
        "total_outcomes": len(outcomes),
        "computed_outcomes": len(computed),
        "horizons": horizon_metrics,
        "warnings": warnings,
        "alert": {
            "should_alert": bool(warnings),
            "severity": "warning" if warnings else "info",
            "reason": (
                "no_computed_outcomes"
                if data_status == "no_computed_outcomes"
                else "metrics_warning" if warnings else "metrics_ok"
            ),
        },
    }


def build_horizon_metrics(outcomes: list[dict], *, horizon: int) -> dict:
    rows = [row for row in outcomes if int(row.get("horizon_trading_days", 0)) == horizon]
    up_rows = [row for row in rows if row.get("up_prediction_correct") is not None]
    actual_up_rows = [row for row in rows if row.get("actual_up") is not None]
    return_error_rows = [row for row in rows if safe_float(row.get("return_error")) is not None]
    probabilities = [
        (
            safe_float(row.get("predicted_up_probability")),
            bool(row.get("actual_up")),
        )
        for row in rows
        if safe_float(row.get("predicted_up_probability")) is not None
        and row.get("actual_up") is not None
    ]

    metrics = {
        "sample_size": len(rows),
        "up_accuracy": ratio(
            sum(1 for row in up_rows if row.get("up_prediction_correct") is True),
            len(up_rows),
        ),
        "direction_accuracy": ratio(
            sum(1 for row in up_rows if row.get("up_prediction_correct") is True),
            len(up_rows),
        ),
        "precision": build_precision(rows),
        "recall": build_recall(rows),
        "roc_auc": build_roc_auc(probabilities),
        "brier_score": build_brier_score(probabilities),
        "return_mae": (
            round(mean(abs(float(row["return_error"])) for row in return_error_rows), 6)
            if return_error_rows
            else None
        ),
        "actual_up_rate": ratio(
            sum(1 for row in actual_up_rows if row.get("actual_up") is True),
            len(actual_up_rows),
        ),
    }
    if horizon == 20:
        metrics.update(build_large_drop_metrics(rows))
    return metrics


def build_large_drop_metrics(rows: list[dict]) -> dict:
    usable_rows = [
        row
        for row in rows
        if row.get("large_drop_prediction_correct") is not None
    ]
    actual_drop_rows = [
        row
        for row in rows
        if safe_float(row.get("actual_max_drop_pct")) is not None
    ]
    predicted_drop_rows = [
        row
        for row in rows
        if safe_float(row.get("predicted_large_drop_risk")) is not None
        and safe_float(row.get("actual_max_drop_pct")) is not None
    ]
    downside_rows = [
        row
        for row in rows
        if get_predicted_max_drop(row) is not None
        and safe_float(row.get("actual_max_drop_pct")) is not None
    ]
    return {
        "large_drop_accuracy": ratio(
            sum(1 for row in usable_rows if row.get("large_drop_prediction_correct") is True),
            len(usable_rows),
        ),
        "large_drop_hit_rate": build_large_drop_hit_rate(predicted_drop_rows),
        "max_drop_mae": build_max_drop_mae(downside_rows),
        "downside_underestimation_rate": build_downside_underestimation_rate(downside_rows),
        "downside_underestimation_sample_size": len(downside_rows),
        "actual_large_drop_rate": ratio(
            sum(1 for row in actual_drop_rows if is_large_drop(row)),
            len(actual_drop_rows),
        ),
    }


def build_precision(rows: list[dict]) -> float | None:
    predicted_positive = [
        row
        for row in rows
        if safe_float(row.get("predicted_up_probability")) is not None
        and safe_float(row.get("predicted_up_probability")) >= 0.5
    ]
    true_positive = sum(1 for row in predicted_positive if row.get("actual_up") is True)
    return ratio(true_positive, len(predicted_positive))


def build_recall(rows: list[dict]) -> float | None:
    actual_positive = [row for row in rows if row.get("actual_up") is True]
    true_positive = sum(
        1
        for row in actual_positive
        if safe_float(row.get("predicted_up_probability")) is not None
        and safe_float(row.get("predicted_up_probability")) >= 0.5
    )
    return ratio(true_positive, len(actual_positive))


def build_large_drop_hit_rate(rows: list[dict]) -> float | None:
    actual_large_drops = [row for row in rows if is_large_drop(row)]
    predicted_hits = sum(
        1
        for row in actual_large_drops
        if safe_float(row.get("predicted_large_drop_risk")) is not None
        and safe_float(row.get("predicted_large_drop_risk")) >= 0.5
    )
    return ratio(predicted_hits, len(actual_large_drops))


def build_max_drop_mae(rows: list[dict]) -> float | None:
    errors = [
        abs(safe_float(row.get("actual_max_drop_pct")) - get_predicted_max_drop(row))
        for row in rows
    ]
    return round(mean(errors), 6) if errors else None


def build_downside_underestimation_rate(rows: list[dict]) -> float | None:
    underestimated = 0
    for row in rows:
        actual = safe_float(row.get("actual_max_drop_pct"))
        predicted = get_predicted_max_drop(row)
        if actual is not None and predicted is not None and actual < predicted - 0.05:
            underestimated += 1
    return ratio(underestimated, len(rows))


def build_roc_auc(probabilities: list[tuple[float | None, bool]]) -> float | None:
    usable = [(float(score), label) for score, label in probabilities if score is not None]
    positives = [score for score, label in usable if label]
    negatives = [score for score, label in usable if not label]
    if not positives or not negatives:
        return None

    wins = 0.0
    total = 0
    for positive_score in positives:
        for negative_score in negatives:
            total += 1
            if positive_score > negative_score:
                wins += 1
            elif positive_score == negative_score:
                wins += 0.5
    return round(wins / total, 6)


def build_brier_score(probabilities: list[tuple[float | None, bool]]) -> float | None:
    usable = [(float(score), 1.0 if label else 0.0) for score, label in probabilities if score is not None]
    if not usable:
        return None
    return round(mean((score - label) ** 2 for score, label in usable), 6)


def build_warnings(horizon_metrics: dict, *, thresholds: dict) -> list[dict]:
    warnings = []
    for horizon, metrics in horizon_metrics.items():
        sample_size = metrics["sample_size"]
        if sample_size == 0:
            continue
        if sample_size < thresholds["min_sample_size"]:
            warnings.append(
                {
                    "source": f"horizon_{horizon}",
                    "status": "warning",
                    "metric": "sample_size",
                    "value": sample_size,
                    "threshold": thresholds["min_sample_size"],
                    "message": f"Horizon {horizon} sample size is below threshold.",
                }
            )

        up_accuracy = metrics.get("up_accuracy")
        if up_accuracy is not None and up_accuracy < thresholds["min_up_accuracy"]:
            warnings.append(
                {
                    "source": f"horizon_{horizon}",
                    "status": "warning",
                    "metric": "up_accuracy",
                    "value": up_accuracy,
                    "threshold": thresholds["min_up_accuracy"],
                    "message": f"Horizon {horizon} up accuracy is below threshold.",
                }
            )

    downside_rate = horizon_metrics.get("20", {}).get("downside_underestimation_rate")
    if (
        downside_rate is not None
        and downside_rate > thresholds["max_downside_underestimation_rate"]
    ):
        warnings.append(
            {
                "source": "horizon_20",
                "status": "warning",
                "metric": "downside_underestimation_rate",
                "value": downside_rate,
                "threshold": thresholds["max_downside_underestimation_rate"],
                "message": "20-day downside underestimation rate is above threshold.",
            }
        )
    return warnings


def build_monitoring_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Monitoring Metrics",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Window days: `{report['window_days']}`",
        f"- Universe: `{report['universe']}`",
        f"- Model version: `{report.get('model_version') or 'all'}`",
        f"- Data status: `{report.get('data_status', 'ready')}`",
        f"- Computed outcomes: `{report['computed_outcomes']}`",
        "",
        "## Horizon Metrics",
        "",
        "| Horizon | Sample | Up Accuracy | ROC AUC | Brier Score | Return MAE | Large Drop Hit Rate | Downside Underestimation |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        metrics = report["horizons"][str(horizon)]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{horizon}d",
                    str(metrics.get("sample_size")),
                    format_percent(metrics.get("up_accuracy")),
                    format_float(metrics.get("roc_auc")),
                    format_float(metrics.get("brier_score")),
                    format_percent(metrics.get("return_mae")),
                    format_percent(metrics.get("large_drop_hit_rate")),
                    format_percent(metrics.get("downside_underestimation_rate")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning['message']} ({warning['metric']}={warning['value']})" for warning in report["warnings"])
    else:
        lines.append("- No warnings.")

    return "\n".join(lines) + "\n"


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def is_large_drop(row: dict) -> bool:
    actual_max_drop = safe_float(row.get("actual_max_drop_pct"))
    return actual_max_drop is not None and actual_max_drop <= -0.08


def get_predicted_max_drop(row: dict) -> float | None:
    direct = safe_float(row.get("predicted_max_drop_20d"))
    if direct is not None:
        return direct
    prediction = row.get("ml_predictions") or row.get("ml_prediction") or {}
    if isinstance(prediction, dict):
        return safe_float(prediction.get("predicted_max_drop_20d"))
    return None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_calibration_report(
    outcomes: list[dict],
    *,
    days: int = 90,
    universe: str = "QQQ100",
    model_version: str | None = None,
    bucket_count: int = 10,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_CALIBRATION_THRESHOLDS, **(thresholds or {})}
    computed = [row for row in outcomes if row.get("outcome_status") == "computed"]
    generated = generated_at or datetime.now(UTC)
    targets = {
        "up_5d": build_target_calibration(computed, target="up_5d", horizon=5, bucket_count=bucket_count),
        "up_10d": build_target_calibration(computed, target="up_10d", horizon=10, bucket_count=bucket_count),
        "up_20d": build_target_calibration(computed, target="up_20d", horizon=20, bucket_count=bucket_count),
        "large_drop_20d": build_target_calibration(
            computed,
            target="large_drop_20d",
            horizon=20,
            bucket_count=bucket_count,
        ),
    }
    warnings = build_calibration_warnings(targets, thresholds=thresholds)
    data_status = "no_computed_outcomes" if not computed else "ready"
    return {
        "report_version": "ml_calibration_report_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "window_days": days,
        "universe": universe,
        "model_version": model_version,
        "data_status": data_status,
        "bucket_count": bucket_count,
        "thresholds": thresholds,
        "total_outcomes": len(outcomes),
        "computed_outcomes": len(computed),
        "targets": targets,
        "warnings": warnings,
        "alert": {
            "should_alert": bool(warnings),
            "severity": "warning" if warnings else "info",
            "reason": (
                "no_computed_outcomes"
                if data_status == "no_computed_outcomes"
                else "calibration_warning" if warnings else "calibration_ok"
            ),
        },
    }


def build_target_calibration(
    outcomes: list[dict],
    *,
    target: str,
    horizon: int,
    bucket_count: int,
) -> dict:
    rows = [
        row
        for row in outcomes
        if int(row.get("horizon_trading_days", 0)) == horizon
    ]
    pairs = [
        pair
        for row in rows
        if (pair := extract_calibration_pair(row, target)) is not None
    ]
    buckets = build_probability_buckets(pairs, bucket_count=bucket_count)
    usable_buckets = [bucket for bucket in buckets if bucket["sample_size"] > 0]
    absolute_errors = [
        abs(bucket["calibration_error"])
        for bucket in usable_buckets
        if bucket["calibration_error"] is not None
    ]
    return {
        "target": target,
        "horizon_trading_days": horizon,
        "usable_sample_size": len(pairs),
        "bucket_count": len(usable_buckets),
        "mean_absolute_calibration_error": (
            round(mean(absolute_errors), 6) if absolute_errors else None
        ),
        "max_calibration_error": (
            round(max(absolute_errors), 6) if absolute_errors else None
        ),
        "buckets": buckets,
    }


def extract_calibration_pair(row: dict, target: str) -> tuple[float, bool] | None:
    if target.startswith("up_"):
        probability = safe_float(row.get("predicted_up_probability"))
        actual = row.get("actual_up")
    elif target == "large_drop_20d":
        probability = safe_float(row.get("predicted_large_drop_risk"))
        actual = is_large_drop(row)
        if safe_float(row.get("actual_max_drop_pct")) is None:
            actual = None
    else:
        return None

    if probability is None or actual is None:
        return None
    return min(max(probability, 0.0), 1.0), bool(actual)


def build_probability_buckets(
    pairs: list[tuple[float, bool]],
    *,
    bucket_count: int,
) -> list[dict]:
    buckets = []
    width = 1.0 / bucket_count
    for index in range(bucket_count):
        low = round(index * width, 10)
        high = round((index + 1) * width, 10)
        bucket_pairs = [
            pair
            for pair in pairs
            if pair_in_bucket(pair[0], low=low, high=high, is_last=index == bucket_count - 1)
        ]
        sample_size = len(bucket_pairs)
        if sample_size:
            avg_probability = mean(pair[0] for pair in bucket_pairs)
            actual_rate = mean(1.0 if pair[1] else 0.0 for pair in bucket_pairs)
            calibration_error = actual_rate - avg_probability
        else:
            avg_probability = None
            actual_rate = None
            calibration_error = None
        buckets.append(
            {
                "bucket": f"{low:.1f}-{high:.1f}",
                "bucket_low": round(low, 3),
                "bucket_high": round(high, 3),
                "sample_size": sample_size,
                "avg_predicted_probability": (
                    round(avg_probability, 6) if avg_probability is not None else None
                ),
                "actual_rate": round(actual_rate, 6) if actual_rate is not None else None,
                "calibration_error": (
                    round(calibration_error, 6) if calibration_error is not None else None
                ),
            }
        )
    return buckets


def pair_in_bucket(probability: float, *, low: float, high: float, is_last: bool) -> bool:
    if is_last:
        return low <= probability <= high
    return low <= probability < high


def build_calibration_warnings(targets: dict, *, thresholds: dict) -> list[dict]:
    warnings = []
    for target, summary in targets.items():
        usable_sample_size = summary["usable_sample_size"]
        mean_error = summary.get("mean_absolute_calibration_error")
        max_error = summary.get("max_calibration_error")
        if (
            usable_sample_size > 0
            and usable_sample_size < thresholds["min_usable_sample_size"]
        ):
            warnings.append(
                {
                    "source": target,
                    "status": "warning",
                    "metric": "usable_sample_size",
                    "value": usable_sample_size,
                    "threshold": thresholds["min_usable_sample_size"],
                    "message": f"{target} usable calibration sample size is below threshold.",
                }
            )
        if (
            mean_error is not None
            and mean_error > thresholds["max_mean_absolute_calibration_error"]
        ):
            warnings.append(
                {
                    "source": target,
                    "status": "warning",
                    "metric": "mean_absolute_calibration_error",
                    "value": mean_error,
                    "threshold": thresholds["max_mean_absolute_calibration_error"],
                    "message": f"{target} mean absolute calibration error is above threshold.",
                }
            )
        if max_error is not None and max_error > thresholds["max_calibration_error"]:
            warnings.append(
                {
                    "source": target,
                    "status": "warning",
                    "metric": "max_calibration_error",
                    "value": max_error,
                    "threshold": thresholds["max_calibration_error"],
                    "message": f"{target} max calibration error is above threshold.",
                }
            )
    return warnings


def build_calibration_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Calibration Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Window days: `{report['window_days']}`",
        f"- Universe: `{report['universe']}`",
        f"- Model version: `{report.get('model_version') or 'all'}`",
        f"- Data status: `{report.get('data_status', 'ready')}`",
        f"- Bucket count: `{report['bucket_count']}`",
        f"- Computed outcomes: `{report['computed_outcomes']}`",
        "",
        "## Target Summary",
        "",
        "| Target | Usable Sample | Buckets | Mean Abs Error | Max Error |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for target, summary in report["targets"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    str(summary["usable_sample_size"]),
                    str(summary["bucket_count"]),
                    format_percent(summary.get("mean_absolute_calibration_error")),
                    format_percent(summary.get("max_calibration_error")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Buckets", ""])
    for target, summary in report["targets"].items():
        lines.extend(
            [
                f"### {target}",
                "",
                "| Bucket | Sample | Avg Predicted | Actual Rate | Error |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for bucket in summary["buckets"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        bucket["bucket"],
                        str(bucket["sample_size"]),
                        format_percent(bucket["avg_predicted_probability"]),
                        format_percent(bucket["actual_rate"]),
                        format_percent(bucket["calibration_error"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning['message']} ({warning['metric']}={warning['value']})" for warning in report["warnings"])
    else:
        lines.append("- No warnings.")

    return "\n".join(lines) + "\n"
