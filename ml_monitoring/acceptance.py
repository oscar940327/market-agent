from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


DEFAULT_ACCEPTANCE_THRESHOLDS = {
    "max_brier_score_regression_ratio": 0.05,
    "max_large_drop_recall_drop": 0.10,
    "min_sample_size": 50,
}
CORE_HORIZONS = ("5", "10", "20")
BLOCKING_CALIBRATION_METRICS = {
    "mean_absolute_calibration_error",
    "max_calibration_error",
}


def build_model_acceptance_report(
    *,
    production_metrics: dict | None = None,
    candidate_metrics: dict | None = None,
    candidate_calibration: dict | None = None,
    drift_report: dict | None = None,
    candidate_model_version: str | None = None,
    production_model_version: str | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_ACCEPTANCE_THRESHOLDS, **(thresholds or {})}
    generated = generated_at or datetime.now(UTC)
    production_model_version = production_model_version or extract_model_version(production_metrics)
    candidate_model_version = candidate_model_version or extract_model_version(candidate_metrics)

    checks = []
    if candidate_metrics is None:
        checks.append(
            build_check(
                name="candidate_metrics_available",
                status="skipped",
                message="No candidate metrics report was provided.",
            )
        )
        return build_report(
            generated=generated,
            production_model_version=production_model_version,
            candidate_model_version=candidate_model_version,
            thresholds=thresholds,
            checks=checks,
            recommendation="no_candidate",
            summary="No candidate model was provided, so no model upgrade review is needed.",
        )

    if production_metrics is None:
        checks.append(
            build_check(
                name="production_metrics_available",
                status="manual_review",
                message="No production metrics report was provided, so the candidate cannot be compared against the current model.",
            )
        )
    else:
        checks.extend(
            build_classification_checks(
                production_metrics=production_metrics,
                candidate_metrics=candidate_metrics,
                thresholds=thresholds,
            )
        )

    checks.extend(build_candidate_health_checks(candidate_metrics, thresholds=thresholds))
    checks.extend(build_calibration_checks(candidate_calibration))
    checks.extend(build_drift_checks(drift_report))
    recommendation = choose_recommendation(checks)
    return build_report(
        generated=generated,
        production_model_version=production_model_version,
        candidate_model_version=candidate_model_version,
        thresholds=thresholds,
        checks=checks,
        recommendation=recommendation,
        summary=build_recommendation_summary(recommendation, checks),
    )


def build_classification_checks(
    *,
    production_metrics: dict,
    candidate_metrics: dict,
    thresholds: dict,
) -> list[dict]:
    checks = []
    for horizon in CORE_HORIZONS:
        production = get_horizon_metrics(production_metrics, horizon)
        candidate = get_horizon_metrics(candidate_metrics, horizon)
        checks.append(
            compare_accuracy(
                horizon=horizon,
                production=production,
                candidate=candidate,
            )
        )
        checks.append(
            compare_brier_score(
                horizon=horizon,
                production=production,
                candidate=candidate,
                thresholds=thresholds,
            )
        )

    production_20 = get_horizon_metrics(production_metrics, "20")
    candidate_20 = get_horizon_metrics(candidate_metrics, "20")
    checks.append(
        compare_large_drop_recall(
            production=production_20,
            candidate=candidate_20,
            thresholds=thresholds,
        )
    )
    return checks


def compare_accuracy(*, horizon: str, production: dict, candidate: dict) -> dict:
    production_value = safe_float(production.get("up_accuracy"))
    candidate_value = safe_float(candidate.get("up_accuracy"))
    if production_value is None or candidate_value is None:
        return build_check(
            name=f"up_accuracy_{horizon}d",
            status="manual_review",
            metric="up_accuracy",
            production_value=production_value,
            candidate_value=candidate_value,
            message=f"{horizon}d up accuracy is missing for production or candidate.",
        )
    if candidate_value < production_value:
        return build_check(
            name=f"up_accuracy_{horizon}d",
            status="reject",
            metric="up_accuracy",
            production_value=production_value,
            candidate_value=candidate_value,
            message=f"{horizon}d up accuracy is lower than production.",
        )
    return build_check(
        name=f"up_accuracy_{horizon}d",
        status="pass",
        metric="up_accuracy",
        production_value=production_value,
        candidate_value=candidate_value,
        message=f"{horizon}d up accuracy is not worse than production.",
    )


def compare_brier_score(*, horizon: str, production: dict, candidate: dict, thresholds: dict) -> dict:
    production_value = safe_float(production.get("brier_score"))
    candidate_value = safe_float(candidate.get("brier_score"))
    if production_value is None or candidate_value is None:
        return build_check(
            name=f"brier_score_{horizon}d",
            status="manual_review",
            metric="brier_score",
            production_value=production_value,
            candidate_value=candidate_value,
            message=f"{horizon}d Brier score is missing for production or candidate.",
        )
    allowed = production_value * (1 + thresholds["max_brier_score_regression_ratio"])
    if production_value == 0:
        allowed = thresholds["max_brier_score_regression_ratio"]
    if candidate_value > allowed:
        return build_check(
            name=f"brier_score_{horizon}d",
            status="reject",
            metric="brier_score",
            production_value=production_value,
            candidate_value=candidate_value,
            threshold=round(allowed, 6),
            message=f"{horizon}d Brier score worsened by more than the allowed threshold.",
        )
    return build_check(
        name=f"brier_score_{horizon}d",
        status="pass",
        metric="brier_score",
        production_value=production_value,
        candidate_value=candidate_value,
        threshold=round(allowed, 6),
        message=f"{horizon}d Brier score is within the allowed threshold.",
    )


def compare_large_drop_recall(*, production: dict, candidate: dict, thresholds: dict) -> dict:
    production_value = safe_float(production.get("large_drop_hit_rate"))
    candidate_value = safe_float(candidate.get("large_drop_hit_rate"))
    if production_value is None or candidate_value is None:
        return build_check(
            name="large_drop_20d_recall",
            status="manual_review",
            metric="large_drop_hit_rate",
            production_value=production_value,
            candidate_value=candidate_value,
            message="20d large-drop recall is missing for production or candidate.",
        )
    allowed_floor = production_value - thresholds["max_large_drop_recall_drop"]
    if candidate_value < allowed_floor:
        return build_check(
            name="large_drop_20d_recall",
            status="reject",
            metric="large_drop_hit_rate",
            production_value=production_value,
            candidate_value=candidate_value,
            threshold=round(allowed_floor, 6),
            message="20d large-drop recall dropped more than the allowed threshold.",
        )
    return build_check(
        name="large_drop_20d_recall",
        status="pass",
        metric="large_drop_hit_rate",
        production_value=production_value,
        candidate_value=candidate_value,
        threshold=round(allowed_floor, 6),
        message="20d large-drop recall is within the allowed threshold.",
    )


def build_candidate_health_checks(candidate_metrics: dict, *, thresholds: dict) -> list[dict]:
    checks = []
    for horizon in CORE_HORIZONS:
        metrics = get_horizon_metrics(candidate_metrics, horizon)
        sample_size = int(metrics.get("sample_size") or 0)
        status = "pass" if sample_size >= thresholds["min_sample_size"] else "manual_review"
        checks.append(
            build_check(
                name=f"sample_size_{horizon}d",
                status=status,
                metric="sample_size",
                candidate_value=sample_size,
                threshold=thresholds["min_sample_size"],
                message=(
                    f"{horizon}d candidate sample size is sufficient."
                    if status == "pass"
                    else f"{horizon}d candidate sample size is below threshold."
                ),
            )
        )
    return checks


def build_calibration_checks(candidate_calibration: dict | None) -> list[dict]:
    if candidate_calibration is None:
        return [
            build_check(
                name="candidate_calibration_available",
                status="manual_review",
                message="No candidate calibration report was provided.",
            )
        ]
    warnings = candidate_calibration.get("warnings") or []
    blocking = [
        warning
        for warning in warnings
        if warning.get("metric") in BLOCKING_CALIBRATION_METRICS
    ]
    if blocking:
        return [
            build_check(
                name="candidate_calibration",
                status="reject",
                metric="calibration_warning",
                candidate_value=len(blocking),
                message="Candidate calibration has blocking warnings.",
                details=blocking,
            )
        ]
    if warnings:
        return [
            build_check(
                name="candidate_calibration",
                status="manual_review",
                metric="calibration_warning",
                candidate_value=len(warnings),
                message="Candidate calibration has non-blocking warnings.",
                details=warnings,
            )
        ]
    return [
        build_check(
            name="candidate_calibration",
            status="pass",
            metric="calibration_warning",
            candidate_value=0,
            message="Candidate calibration has no warnings.",
        )
    ]


def build_drift_checks(drift_report: dict | None) -> list[dict]:
    if drift_report is None:
        return [
            build_check(
                name="drift_report_available",
                status="manual_review",
                message="No drift report was provided.",
            )
        ]
    warnings = drift_report.get("warnings") or []
    if warnings:
        return [
            build_check(
                name="drift_warning",
                status="manual_review",
                metric="drift_warning",
                candidate_value=len(warnings),
                message="Current data has drift warnings, so promotion needs manual review.",
                details=warnings,
            )
        ]
    return [
        build_check(
            name="drift_warning",
            status="pass",
            metric="drift_warning",
            candidate_value=0,
            message="Current data has no drift warnings.",
        )
    ]


def choose_recommendation(checks: list[dict]) -> str:
    statuses = {check["status"] for check in checks}
    if "skipped" in statuses:
        return "no_candidate"
    if "reject" in statuses:
        return "reject"
    if "manual_review" in statuses:
        return "manual_review"
    return "promote"


def build_recommendation_summary(recommendation: str, checks: list[dict]) -> str:
    failed = [check for check in checks if check["status"] == "reject"]
    review = [check for check in checks if check["status"] == "manual_review"]
    if recommendation == "promote":
        return "Candidate model passed the first-version upgrade checks. Manual approval is still required before replacing production."
    if recommendation == "reject":
        return f"Candidate model should not replace production. Blocking checks: {len(failed)}."
    if recommendation == "manual_review":
        return f"Candidate model needs manual review before any upgrade. Review checks: {len(review)}."
    return "No candidate model was provided, so no model upgrade review was needed."


def build_model_acceptance_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Model Upgrade Review",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Production model: `{report.get('production_model_version') or 'unknown'}`",
        f"- Candidate model: `{report.get('candidate_model_version') or 'unknown'}`",
        f"- Recommendation: `{report['recommendation']}`",
        f"- Summary: {report['summary']}",
        "",
        "## Checks",
        "",
        "| Check | Status | Metric | Production | Candidate | Threshold | Message |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for check in report["checks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    check["name"],
                    check["status"],
                    str(check.get("metric") or ""),
                    format_value(check.get("production_value")),
                    format_value(check.get("candidate_value")),
                    format_value(check.get("threshold")),
                    check["message"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Email Summary",
            "",
            build_model_acceptance_email_summary(report),
        ]
    )
    return "\n".join(lines) + "\n"


def build_model_acceptance_email_summary(report: dict) -> str:
    recommendation = report["recommendation"]
    lines = [
        f"Model upgrade review recommendation: {recommendation}.",
        report["summary"],
    ]
    action_checks = [
        check
        for check in report["checks"]
        if check["status"] in {"reject", "manual_review"}
    ]
    if action_checks:
        lines.append("Checks needing attention:")
        lines.extend(f"- {check['name']}: {check['message']}" for check in action_checks[:8])
    return "\n".join(lines)


def build_report(
    *,
    generated: datetime,
    production_model_version: str | None,
    candidate_model_version: str | None,
    thresholds: dict,
    checks: list[dict],
    recommendation: str,
    summary: str,
) -> dict:
    should_alert = recommendation in {"promote", "reject", "manual_review"}
    return {
        "report_version": "ml_model_upgrade_review_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "production_model_version": production_model_version,
        "candidate_model_version": candidate_model_version,
        "thresholds": thresholds,
        "recommendation": recommendation,
        "summary": summary,
        "checks": checks,
        "alert": {
            "should_alert": should_alert,
            "severity": "warning" if recommendation in {"reject", "manual_review"} else "info",
            "reason": f"model_upgrade_{recommendation}",
        },
    }


def build_check(
    *,
    name: str,
    status: str,
    message: str,
    metric: str | None = None,
    production_value: Any = None,
    candidate_value: Any = None,
    threshold: Any = None,
    details: list[dict] | None = None,
) -> dict:
    check = {
        "name": name,
        "status": status,
        "message": message,
    }
    if metric is not None:
        check["metric"] = metric
    if production_value is not None:
        check["production_value"] = production_value
    if candidate_value is not None:
        check["candidate_value"] = candidate_value
    if threshold is not None:
        check["threshold"] = threshold
    if details is not None:
        check["details"] = details
    return check


def extract_model_version(report: dict | None) -> str | None:
    if not report:
        return None
    return report.get("model_version")


def get_horizon_metrics(report: dict, horizon: str) -> dict:
    return (report.get("horizons") or {}).get(horizon) or {}


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
