from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ml_monitoring import build_calibration_report


DEFAULT_THRESHOLDS = {
    "min_bucket_sample_size": 20,
    "large_adjustment_threshold": 0.10,
}


def build_step20_calibration_action_report(
    outcomes: list[dict],
    *,
    days: int = 90,
    universe: str = "QQQ100",
    model_version: str | None = None,
    bucket_count: int = 10,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    generated = generated_at or datetime.now(UTC)
    calibration = build_calibration_report(
        outcomes,
        days=days,
        universe=universe,
        model_version=model_version,
        bucket_count=bucket_count,
        generated_at=generated,
    )
    target_actions = {
        target: build_target_calibration_actions(summary, thresholds=thresholds)
        for target, summary in calibration["targets"].items()
    }
    findings = build_calibration_action_findings(target_actions)
    return {
        "report_version": "step20_calibration_action_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "window_days": days,
        "universe": universe,
        "model_version": model_version,
        "thresholds": thresholds,
        "source_calibration_report": calibration,
        "target_actions": target_actions,
        "findings": findings,
        "next_actions": build_next_actions(findings),
    }


def build_target_calibration_actions(summary: dict, *, thresholds: dict) -> dict:
    actions = []
    usable_count = 0
    large_adjustment_count = 0
    for bucket in summary.get("buckets") or []:
        action = build_bucket_action(bucket, thresholds=thresholds)
        actions.append(action)
        if action["status"] == "usable":
            usable_count += 1
        if action.get("adjustment_size") is not None and action["adjustment_size"] >= thresholds["large_adjustment_threshold"]:
            large_adjustment_count += 1

    recommendation = "use_conservative_wording"
    if usable_count >= 2 and large_adjustment_count == 0:
        recommendation = "calibration_table_usable"
    elif usable_count >= 2:
        recommendation = "calibration_table_usable_but_large_adjustments"
    elif summary.get("usable_sample_size", 0) > 0:
        recommendation = "insufficient_bucket_coverage"

    return {
        "target": summary["target"],
        "horizon_trading_days": summary["horizon_trading_days"],
        "usable_sample_size": summary["usable_sample_size"],
        "mean_absolute_calibration_error": summary.get("mean_absolute_calibration_error"),
        "max_calibration_error": summary.get("max_calibration_error"),
        "usable_bucket_count": usable_count,
        "large_adjustment_count": large_adjustment_count,
        "recommendation": recommendation,
        "bucket_actions": actions,
    }


def build_bucket_action(bucket: dict, *, thresholds: dict) -> dict:
    sample_size = int(bucket.get("sample_size") or 0)
    avg_probability = safe_float(bucket.get("avg_predicted_probability"))
    actual_rate = safe_float(bucket.get("actual_rate"))
    calibration_error = safe_float(bucket.get("calibration_error"))
    if sample_size < thresholds["min_bucket_sample_size"] or avg_probability is None or actual_rate is None:
        return {
            "bucket": bucket["bucket"],
            "sample_size": sample_size,
            "status": "insufficient_sample",
            "avg_predicted_probability": avg_probability,
            "actual_rate": actual_rate,
            "suggested_probability": None,
            "adjustment": None,
            "adjustment_size": None,
            "display_policy": "do_not_use_bucket_adjustment",
        }

    adjustment = actual_rate - avg_probability
    adjustment_size = abs(adjustment)
    display_policy = "use_calibrated_probability"
    if adjustment_size >= thresholds["large_adjustment_threshold"]:
        display_policy = "use_calibrated_probability_with_reduced_trust"

    return {
        "bucket": bucket["bucket"],
        "sample_size": sample_size,
        "status": "usable",
        "avg_predicted_probability": avg_probability,
        "actual_rate": actual_rate,
        "suggested_probability": round(actual_rate, 6),
        "adjustment": round(adjustment, 6),
        "adjustment_size": round(adjustment_size, 6),
        "calibration_error": calibration_error,
        "display_policy": display_policy,
    }


def build_calibration_action_findings(target_actions: dict) -> list[dict]:
    findings = []
    for target, action in target_actions.items():
        if action["recommendation"] == "insufficient_bucket_coverage":
            findings.append(
                {
                    "source": "bucket_coverage",
                    "severity": "warning",
                    "target": target,
                    "message": f"{target} has too few usable calibration buckets.",
                }
            )
        if action["large_adjustment_count"] > 0:
            findings.append(
                {
                    "source": "large_calibration_adjustment",
                    "severity": "warning",
                    "target": target,
                    "message": f"{target} has {action['large_adjustment_count']} large calibration adjustment(s).",
                }
            )
    return findings


def build_next_actions(findings: list[dict]) -> list[str]:
    sources = {finding["source"] for finding in findings}
    actions = []
    if "large_calibration_adjustment" in sources:
        actions.append("Show calibrated probabilities as reduced-trust until more outcomes accumulate.")
    if "bucket_coverage" in sources:
        actions.append("Keep raw probability wording conservative for sparse calibration buckets.")
    if not actions:
        actions.append("Calibration table is usable as a first-pass probability adjustment reference.")
    actions.append("Do not replace raw model probabilities until calibrated output is tested in reports.")
    return dedupe(actions)


def build_step20_calibration_action_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 20 Calibration Action Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Universe: `{report['universe']}`",
        f"- Model version: `{report.get('model_version') or 'all_models'}`",
        f"- Window days: `{report['window_days']}`",
        f"- Findings: `{len(report['findings'])}`",
        "",
        "## Target Actions",
        "",
        "| Target | Samples | Usable Buckets | Mean Abs Error | Max Error | Recommendation |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for target, action in report["target_actions"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    str(action["usable_sample_size"]),
                    str(action["usable_bucket_count"]),
                    format_percent(action.get("mean_absolute_calibration_error")),
                    format_percent(action.get("max_calibration_error")),
                    action["recommendation"],
                ]
            )
            + " |"
        )

    lines.extend(["", "## Bucket Adjustments", ""])
    for target, action in report["target_actions"].items():
        lines.extend([f"### {target}", ""])
        lines.extend(
            [
                "| Bucket | Samples | Avg Predicted | Actual Rate | Suggested | Adjustment | Policy |",
                "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for bucket in action["bucket_actions"]:
            if bucket["status"] != "usable":
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        bucket["bucket"],
                        str(bucket["sample_size"]),
                        format_percent(bucket.get("avg_predicted_probability")),
                        format_percent(bucket.get("actual_rate")),
                        format_percent(bucket.get("suggested_probability")),
                        format_signed_percent(bucket.get("adjustment")),
                        bucket["display_policy"],
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Findings", ""])
    if report["findings"]:
        lines.extend(
            f"- {finding['severity']} / {finding['target']}: {finding['message']}"
            for finding in report["findings"]
        )
    else:
        lines.append("- No findings.")

    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_percent(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed * 100:.1f}%"


def format_signed_percent(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed * 100:+.1f}%"


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
