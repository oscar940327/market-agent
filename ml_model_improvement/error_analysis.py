from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any


HORIZONS = (5, 10, 20)
DEFAULT_THRESHOLDS = {
    "min_group_sample_size": 10,
    "min_up_accuracy": 0.50,
    "max_downside_underestimation_rate": 0.20,
    "max_mean_calibration_error": 0.10,
}
GROUP_DIMENSIONS = (
    "ticker",
    "market_regime",
    "technical_state",
    "news_state",
    "risk_state",
)


def build_step20_error_analysis_report(
    outcomes: list[dict],
    *,
    days: int = 90,
    universe: str = "QQQ100",
    model_version: str | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    computed = [row for row in outcomes if row.get("outcome_status") == "computed"]
    generated = generated_at or datetime.now(UTC)
    horizon_summary = {
        str(horizon): summarize_horizon(computed, horizon=horizon)
        for horizon in HORIZONS
    }
    group_breakdowns = {
        dimension: build_group_breakdown(
            computed,
            dimension=dimension,
            thresholds=thresholds,
        )
        for dimension in GROUP_DIMENSIONS
    }
    findings = build_error_findings(
        horizon_summary=horizon_summary,
        group_breakdowns=group_breakdowns,
        thresholds=thresholds,
    )
    return {
        "report_version": "step20_ml_error_analysis_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "window_days": days,
        "universe": universe,
        "model_version": model_version,
        "thresholds": thresholds,
        "total_outcomes": len(outcomes),
        "computed_outcomes": len(computed),
        "horizon_summary": horizon_summary,
        "group_breakdowns": group_breakdowns,
        "findings": findings,
        "next_actions": build_next_actions(findings),
    }


def summarize_horizon(outcomes: list[dict], *, horizon: int) -> dict:
    rows = [
        row
        for row in outcomes
        if int(row.get("horizon_trading_days") or 0) == horizon
    ]
    up_rows = [
        row
        for row in rows
        if row.get("actual_up") is not None
        and safe_float(row.get("predicted_up_probability")) is not None
    ]
    false_positive_rows = [
        row
        for row in up_rows
        if safe_float(row.get("predicted_up_probability")) >= 0.5
        and row.get("actual_up") is False
    ]
    false_negative_rows = [
        row
        for row in up_rows
        if safe_float(row.get("predicted_up_probability")) < 0.5
        and row.get("actual_up") is True
    ]
    probabilities = [
        safe_float(row.get("predicted_up_probability"))
        for row in up_rows
        if safe_float(row.get("predicted_up_probability")) is not None
    ]
    calibration_errors = [
        abs(float(row.get("actual_up")) - safe_float(row.get("predicted_up_probability")))
        for row in up_rows
        if safe_float(row.get("predicted_up_probability")) is not None
    ]
    payload = {
        "sample_size": len(rows),
        "up_sample_size": len(up_rows),
        "up_accuracy": ratio(
            sum(1 for row in up_rows if row.get("up_prediction_correct") is True),
            len(up_rows),
        ),
        "actual_up_rate": ratio(
            sum(1 for row in up_rows if row.get("actual_up") is True),
            len(up_rows),
        ),
        "average_predicted_up_probability": rounded_mean(probabilities),
        "false_positive_rate": ratio(len(false_positive_rows), len(up_rows)),
        "false_negative_rate": ratio(len(false_negative_rows), len(up_rows)),
        "mean_absolute_probability_error": rounded_mean(calibration_errors),
    }
    if horizon == 20:
        payload.update(summarize_downside(rows))
    return payload


def summarize_downside(rows: list[dict]) -> dict:
    downside_rows = [
        row
        for row in rows
        if get_predicted_max_drop(row) is not None
        and safe_float(row.get("actual_max_drop_pct")) is not None
    ]
    underestimated = [
        row
        for row in downside_rows
        if safe_float(row.get("actual_max_drop_pct")) < get_predicted_max_drop(row)
    ]
    return {
        "downside_sample_size": len(downside_rows),
        "downside_underestimation_rate": ratio(len(underestimated), len(downside_rows)),
        "average_actual_max_drop": rounded_mean(
            [
                safe_float(row.get("actual_max_drop_pct"))
                for row in downside_rows
                if safe_float(row.get("actual_max_drop_pct")) is not None
            ]
        ),
        "average_predicted_max_drop": rounded_mean(
            [
                get_predicted_max_drop(row)
                for row in downside_rows
                if get_predicted_max_drop(row) is not None
            ]
        ),
    }


def build_group_breakdown(
    outcomes: list[dict],
    *,
    dimension: str,
    thresholds: dict,
) -> dict:
    groups = {}
    for row in outcomes:
        key = extract_dimension_value(row, dimension)
        groups.setdefault(key, []).append(row)

    summaries = []
    for value, rows in groups.items():
        horizon_payload = {
            str(horizon): summarize_horizon(rows, horizon=horizon)
            for horizon in HORIZONS
        }
        summary = {
            "value": value,
            "sample_size": len(rows),
            "horizons": horizon_payload,
            "worst_error_rate": max(
                [
                    1 - metrics["up_accuracy"]
                    for metrics in horizon_payload.values()
                    if metrics.get("up_accuracy") is not None
                ]
                or [None]
            ),
            "max_downside_underestimation_rate": horizon_payload["20"].get(
                "downside_underestimation_rate"
            ),
        }
        summaries.append(summary)

    summaries = sorted(
        summaries,
        key=lambda item: (
            item["sample_size"] < thresholds["min_group_sample_size"],
            -(item["worst_error_rate"] or -1),
            -(item["max_downside_underestimation_rate"] or -1),
            str(item["value"]),
        ),
    )
    return {
        "dimension": dimension,
        "groups": summaries,
        "worst_groups": [
            group
            for group in summaries
            if group["sample_size"] >= thresholds["min_group_sample_size"]
        ][:5],
    }


def build_error_findings(
    *,
    horizon_summary: dict,
    group_breakdowns: dict,
    thresholds: dict,
) -> list[dict]:
    findings = []
    for horizon, summary in horizon_summary.items():
        up_accuracy = summary.get("up_accuracy")
        if up_accuracy is not None and up_accuracy < thresholds["min_up_accuracy"]:
            findings.append(
                {
                    "source": "horizon_accuracy",
                    "severity": "warning",
                    "target": f"up_{horizon}d",
                    "message": f"{horizon}-day up accuracy is below threshold.",
                    "value": up_accuracy,
                    "threshold": thresholds["min_up_accuracy"],
                }
            )
        calibration_error = summary.get("mean_absolute_probability_error")
        if (
            calibration_error is not None
            and calibration_error > thresholds["max_mean_calibration_error"]
        ):
            findings.append(
                {
                    "source": "probability_calibration",
                    "severity": "warning",
                    "target": f"up_{horizon}d",
                    "message": f"{horizon}-day probability error is above threshold.",
                    "value": calibration_error,
                    "threshold": thresholds["max_mean_calibration_error"],
                }
            )

    downside_rate = horizon_summary["20"].get("downside_underestimation_rate")
    if (
        downside_rate is not None
        and downside_rate > thresholds["max_downside_underestimation_rate"]
    ):
        findings.append(
            {
                "source": "downside_risk",
                "severity": "critical",
                "target": "max_drop_20d",
                "message": "20-day downside underestimation is above threshold.",
                "value": downside_rate,
                "threshold": thresholds["max_downside_underestimation_rate"],
            }
        )

    for dimension, breakdown in group_breakdowns.items():
        worst = (breakdown.get("worst_groups") or [])[:1]
        if not worst:
            continue
        group = worst[0]
        if (group.get("worst_error_rate") or 0) > 0.50:
            findings.append(
                {
                    "source": "group_error",
                    "severity": "warning",
                    "target": dimension,
                    "message": f"{dimension}={group['value']} has high classification error.",
                    "value": group.get("worst_error_rate"),
                    "sample_size": group.get("sample_size"),
                }
            )

    return findings


def build_next_actions(findings: list[dict]) -> list[str]:
    sources = {finding["source"] for finding in findings}
    actions = []
    if "downside_risk" in sources:
        actions.append(
            "Build a downside risk overlay before trusting 20-day max-drop outputs."
        )
    if "probability_calibration" in sources:
        actions.append(
            "Add calibrated probability outputs or conservative probability wording."
        )
    if "horizon_accuracy" in sources:
        actions.append(
            "Review feature importance and candidate models for weak horizon targets."
        )
    if "group_error" in sources:
        actions.append(
            "Prioritize groups with high error rates in the next feature / candidate model pass."
        )
    if not actions:
        actions.append("No major error-analysis blockers; continue candidate model comparison.")
    return dedupe(actions)


def build_step20_error_analysis_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 20 ML Error Analysis",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Universe: `{report['universe']}`",
        f"- Model version: `{report.get('model_version') or 'all_models'}`",
        f"- Window days: `{report['window_days']}`",
        f"- Computed outcomes: `{report['computed_outcomes']}`",
        f"- Findings: `{len(report['findings'])}`",
        "",
        "## Horizon Summary",
        "",
        "| Horizon | Samples | Up Accuracy | Actual Up Rate | Avg Probability | False Positive | False Negative | Probability Error | Downside Underestimation |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        summary = report["horizon_summary"][str(horizon)]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{horizon}d",
                    str(summary["sample_size"]),
                    format_percent(summary.get("up_accuracy")),
                    format_percent(summary.get("actual_up_rate")),
                    format_percent(summary.get("average_predicted_up_probability")),
                    format_percent(summary.get("false_positive_rate")),
                    format_percent(summary.get("false_negative_rate")),
                    format_percent(summary.get("mean_absolute_probability_error")),
                    format_percent(summary.get("downside_underestimation_rate")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Worst Groups", ""])
    for dimension in GROUP_DIMENSIONS:
        lines.extend([f"### {dimension}", ""])
        groups = report["group_breakdowns"][dimension]["worst_groups"]
        if not groups:
            lines.append("- No groups with enough samples.")
            lines.append("")
            continue
        lines.extend(
            [
                "| Value | Samples | Worst Error Rate | 20d Downside Underestimation |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for group in groups:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(group["value"]),
                        str(group["sample_size"]),
                        format_percent(group.get("worst_error_rate")),
                        format_percent(group.get("max_downside_underestimation_rate")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Findings", ""])
    if report["findings"]:
        lines.extend(
            f"- {item['severity']} / {item['target']}: {item['message']} "
            f"(value={format_percent(item.get('value'))})"
            for item in report["findings"]
        )
    else:
        lines.append("- No findings.")

    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def extract_dimension_value(row: dict, dimension: str) -> str:
    if dimension == "ticker":
        return str(row.get("ticker") or "unknown").upper()

    snapshot = extract_feature_snapshot(row)
    market_snapshot = snapshot.get("market_snapshot") or {}
    if dimension in market_snapshot:
        return str(market_snapshot.get(dimension) or "unknown")
    return str(snapshot.get(dimension) or "unknown")


def extract_feature_snapshot(row: dict) -> dict:
    if isinstance(row.get("feature_snapshot"), dict):
        return row["feature_snapshot"]
    prediction = row.get("ml_predictions") or {}
    snapshot = prediction.get("feature_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def get_predicted_max_drop(row: dict) -> float | None:
    direct_value = safe_float(row.get("predicted_max_drop_20d"))
    if direct_value is not None:
        return direct_value
    prediction = row.get("ml_predictions") or {}
    return safe_float(prediction.get("predicted_max_drop_20d"))


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def rounded_mean(values: list[float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    return round(mean(usable), 6)


def format_percent(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed * 100:.1f}%"


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
