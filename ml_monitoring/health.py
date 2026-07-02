from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


STATUS_PRIORITY = {
    "healthy": 0,
    "warning": 1,
    "unknown": 2,
    "degraded": 3,
    "unavailable": 4,
}
ALERTABLE_STATUSES = {"warning", "degraded", "unavailable", "unknown"}
DEGRADED_METRICS = {
    "up_accuracy",
    "downside_underestimation_rate",
    "mean_absolute_calibration_error",
    "max_calibration_error",
}


def build_ml_health_report(
    *,
    metrics_report: dict | None = None,
    calibration_report: dict | None = None,
    drift_report: dict | None = None,
    model_upgrade_report: dict | None = None,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    components = {
        "model_quality": evaluate_metrics_report(metrics_report),
        "calibration": evaluate_calibration_report(calibration_report),
        "drift": evaluate_drift_report(drift_report),
        "model_upgrade": evaluate_model_upgrade_report(model_upgrade_report),
    }
    overall_status = combine_statuses(component["status"] for component in components.values())
    warnings = collect_warnings(components)
    action_needed = build_action_needed(components, overall_status=overall_status)
    ml_reference_policy = build_ml_reference_policy(overall_status, components)
    return {
        "report_version": "ml_health_report_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "overall_status": overall_status,
        "ml_reference_policy": ml_reference_policy,
        "components": components,
        "warnings": warnings,
        "action_needed": action_needed,
        "alert": {
            "should_alert": overall_status in ALERTABLE_STATUSES,
            "severity": classify_alert_severity(overall_status),
            "reason": f"ml_health_{overall_status}",
        },
    }


def evaluate_metrics_report(report: dict | None) -> dict:
    if not report:
        return build_component(
            name="model_quality",
            status="unknown",
            summary="Metrics report is missing.",
            action="Build ML monitoring metrics report.",
        )
    warnings = report.get("warnings") or []
    status = classify_warning_status(warnings)
    computed_outcomes = report.get("computed_outcomes", 0)
    if not warnings and computed_outcomes == 0:
        status = "unknown"
    return build_component(
        name="model_quality",
        status=status,
        summary=(
            f"Metrics report has {len(warnings)} warning(s), "
            f"computed_outcomes={computed_outcomes}."
        ),
        warnings=warnings,
        source_report_version=report.get("report_version"),
        action=(
            "Review model metrics warnings."
            if warnings
            else "No action needed for model metrics."
        ),
    )


def evaluate_calibration_report(report: dict | None) -> dict:
    if not report:
        return build_component(
            name="calibration",
            status="unknown",
            summary="Calibration report is missing.",
            action="Build ML calibration report.",
        )
    warnings = report.get("warnings") or []
    status = classify_warning_status(warnings)
    return build_component(
        name="calibration",
        status=status,
        summary=f"Calibration report has {len(warnings)} warning(s).",
        warnings=warnings,
        source_report_version=report.get("report_version"),
        action=(
            "Review calibration buckets and probability quality."
            if warnings
            else "No action needed for calibration."
        ),
    )


def evaluate_drift_report(report: dict | None) -> dict:
    if not report:
        return build_component(
            name="drift",
            status="unknown",
            summary="Drift report is missing.",
            action="Build ML drift report.",
        )
    warnings = report.get("warnings") or []
    status = "degraded" if warnings else "healthy"
    return build_component(
        name="drift",
        status=status,
        summary=(
            f"Drift report has {len(warnings)} warning(s), "
            f"recent_rows={report.get('recent_rows')}, baseline_rows={report.get('baseline_rows')}."
        ),
        warnings=warnings,
        source_report_version=report.get("report_version"),
        action=(
            "Review feature, market regime, news coverage, or freshness drift."
            if warnings
            else "No action needed for drift."
        ),
    )


def evaluate_model_upgrade_report(report: dict | None) -> dict:
    if not report:
        return build_component(
            name="model_upgrade",
            status="unknown",
            summary="Model upgrade review report is missing.",
            action="Build model upgrade review report.",
        )
    recommendation = report.get("recommendation", "unknown")
    if recommendation == "no_candidate":
        status = "healthy"
    elif recommendation == "promote":
        status = "warning"
    elif recommendation in {"manual_review", "reject"}:
        status = "warning"
    else:
        status = "unknown"
    checks = [
        check
        for check in report.get("checks", [])
        if check.get("status") in {"reject", "manual_review"}
    ]
    return build_component(
        name="model_upgrade",
        status=status,
        summary=f"Model upgrade recommendation is {recommendation}.",
        warnings=checks,
        source_report_version=report.get("report_version"),
        action=build_model_upgrade_action(recommendation),
    )


def build_component(
    *,
    name: str,
    status: str,
    summary: str,
    action: str,
    warnings: list[dict] | None = None,
    source_report_version: str | None = None,
) -> dict:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "source_report_version": source_report_version,
        "warnings": warnings or [],
        "action": action,
    }


def classify_warning_status(warnings: list[dict]) -> str:
    if not warnings:
        return "healthy"
    if any(warning.get("metric") in DEGRADED_METRICS for warning in warnings):
        return "degraded"
    return "warning"


def combine_statuses(statuses) -> str:
    return max(statuses, key=lambda status: STATUS_PRIORITY.get(status, 2))


def collect_warnings(components: dict[str, dict]) -> list[dict]:
    warnings = []
    for component_name, component in components.items():
        if component["status"] in ALERTABLE_STATUSES:
            warnings.append(
                {
                    "source": component_name,
                    "status": component["status"],
                    "message": component["summary"],
                    "action": component["action"],
                }
            )
        for warning in component.get("warnings", []):
            warnings.append(
                {
                    "source": component_name,
                    "status": warning.get("status", component["status"]),
                    "metric": warning.get("metric") or warning.get("name"),
                    "message": warning.get("message", component["summary"]),
                    "action": component["action"],
                }
            )
    return warnings


def build_action_needed(components: dict[str, dict], *, overall_status: str) -> list[str]:
    if overall_status == "healthy":
        return ["No action needed. ML monitoring reports are healthy."]

    actions = []
    for component in components.values():
        if component["status"] != "healthy":
            actions.append(component["action"])
    return dedupe(actions)


def build_ml_reference_policy(overall_status: str, components: dict[str, dict]) -> dict:
    if overall_status == "healthy":
        return {
            "status": "normal",
            "reason": "All ML monitoring components are healthy.",
            "display_note": "ML Reference can be shown normally.",
        }
    if overall_status in {"warning", "degraded"}:
        return {
            "status": "reduced_trust",
            "reason": build_policy_reason(components),
            "display_note": "ML Reference can be shown, but confidence should be reduced.",
        }
    return {
        "status": "unavailable",
        "reason": build_policy_reason(components),
        "display_note": "ML Reference should not be treated as reliable until reports are complete.",
    }


def build_policy_reason(components: dict[str, dict]) -> str:
    affected = [
        f"{name}={component['status']}"
        for name, component in components.items()
        if component["status"] != "healthy"
    ]
    return "; ".join(affected) if affected else "No affected components."


def build_model_upgrade_action(recommendation: str) -> str:
    if recommendation == "promote":
        return "Review candidate model before manual promotion."
    if recommendation == "reject":
        return "Do not promote candidate model; review blocking checks."
    if recommendation == "manual_review":
        return "Manually review candidate model checks before any promotion."
    if recommendation == "no_candidate":
        return "No candidate model action needed."
    return "Review model upgrade report."


def classify_alert_severity(overall_status: str) -> str:
    if overall_status in {"degraded", "unavailable"}:
        return "critical"
    if overall_status in {"warning", "unknown"}:
        return "warning"
    return "info"


def build_ml_health_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Health Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- ML Reference policy: `{report['ml_reference_policy']['status']}`",
        f"- Policy reason: {report['ml_reference_policy']['reason']}",
        "",
        "## Components",
        "",
        "| Component | Status | Summary | Action |",
        "| --- | --- | --- | --- |",
    ]
    for component in report["components"].values():
        lines.append(
            "| "
            + " | ".join(
                [
                    component["name"],
                    component["status"],
                    component["summary"],
                    component["action"],
                ]
            )
            + " |"
        )

    lines.extend(["", "## Action Needed", ""])
    lines.extend(f"- {action}" for action in report["action_needed"])

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(
            f"- {warning['source']}: {warning['message']}"
            for warning in report["warnings"]
        )
    else:
        lines.append("- No warnings.")
    return "\n".join(lines) + "\n"


def build_ml_health_email_summary(report: dict) -> str:
    lines = [
        f"ML health status: {report['overall_status']}.",
        f"ML Reference policy: {report['ml_reference_policy']['status']}.",
        f"Reason: {report['ml_reference_policy']['reason']}",
        "",
        "Action needed:",
        *[f"- {action}" for action in report["action_needed"]],
    ]
    if report["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend(
            f"- {warning['source']}: {warning['message']}"
            for warning in report["warnings"][:8]
        )
    return "\n".join(lines)


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    return str(value)
