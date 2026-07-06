from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ml_model_improvement.target_spec import TARGET_METRIC_SPECS


CLASSIFICATION_TARGETS = ("up_5d", "up_10d", "up_20d", "large_drop_20d")
REGRESSION_TARGETS = (
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "max_drop_20d",
)


def build_baseline_audit_report(
    *,
    baseline_metrics: dict | None = None,
    return_model_metrics: dict | None = None,
    monitoring_metrics: dict | None = None,
    calibration_report: dict | None = None,
    health_report: dict | None = None,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    classification = {
        target: audit_classification_target(baseline_metrics or {}, target)
        for target in CLASSIFICATION_TARGETS
    }
    regression = {
        target: audit_regression_target(return_model_metrics or {}, target)
        for target in REGRESSION_TARGETS
    }
    monitoring_findings = audit_monitoring_reports(
        monitoring_metrics=monitoring_metrics,
        calibration_report=calibration_report,
        health_report=health_report,
    )
    findings = collect_findings(classification, regression, monitoring_findings)
    return {
        "report_version": "step15_baseline_audit_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "baseline_model_version": (baseline_metrics or {}).get("model_version"),
        "return_model_version": (return_model_metrics or {}).get("model_version"),
        "classification_targets": classification,
        "regression_targets": regression,
        "monitoring": monitoring_findings,
        "finding_summary": summarize_findings(findings),
        "findings": findings,
        "next_actions": build_next_actions(findings),
    }


def audit_classification_target(metrics_report: dict, target: str) -> dict:
    target_result = (metrics_report.get("targets") or {}).get(target) or {}
    if target_result.get("status") != "success":
        return {
            "status": "missing",
            "reason": target_result.get("reason") or "target_metrics_missing",
            "best_model": None,
            "test_metrics": {},
            "issues": ["target metrics are missing or not successful"],
        }

    models = target_result.get("models") or {}
    best_name, best_payload = choose_best_classification_model(models)
    test_metrics = ((best_payload or {}).get("metrics") or {}).get("test") or {}
    floor = TARGET_METRIC_SPECS[target]["promotion_floor"]
    issues = []
    roc_auc = safe_float(test_metrics.get("roc_auc"))
    accuracy = safe_float(test_metrics.get("accuracy"))
    if "test_roc_auc" in floor:
        if roc_auc is None:
            issues.append("test ROC AUC is missing")
        elif roc_auc < floor["test_roc_auc"]:
            issues.append(f"test ROC AUC {roc_auc:.3f} is below floor {floor['test_roc_auc']:.3f}")
    if "test_accuracy" in floor:
        if accuracy is None:
            issues.append("test accuracy is missing")
        elif accuracy < floor["test_accuracy"]:
            issues.append(f"test accuracy {accuracy:.3f} is below floor {floor['test_accuracy']:.3f}")
    large_drop_hit_rate = safe_float(test_metrics.get("large_drop_hit_rate"))
    if "large_drop_hit_rate" in floor:
        if large_drop_hit_rate is None:
            issues.append("large-drop hit rate is missing")
        elif large_drop_hit_rate < floor["large_drop_hit_rate"]:
            issues.append(
                f"large-drop hit rate {large_drop_hit_rate:.3f} is below floor {floor['large_drop_hit_rate']:.3f}"
            )

    return {
        "status": "warning" if issues else "usable",
        "best_model": best_name,
        "test_metrics": test_metrics,
        "positive_rate": target_result.get("positive_rates", {}).get("test"),
        "row_counts": target_result.get("row_counts", {}),
        "issues": issues,
    }


def choose_best_classification_model(models: dict) -> tuple[str | None, dict | None]:
    candidates = [
        (name, payload)
        for name, payload in models.items()
        if name != "rule_based"
    ]
    if not candidates:
        candidates = list(models.items())
    if not candidates:
        return None, None

    def sort_key(item):
        payload = item[1]
        metrics = (payload.get("metrics") or {}).get("test") or {}
        roc_auc = safe_float(metrics.get("roc_auc"))
        accuracy = safe_float(metrics.get("accuracy"))
        return (
            -1 if roc_auc is None else roc_auc,
            -1 if accuracy is None else accuracy,
        )

    return max(candidates, key=sort_key)


def audit_regression_target(metrics_report: dict, target: str) -> dict:
    target_result = (metrics_report.get("targets") or {}).get(target) or {}
    if target_result.get("status") != "success":
        return {
            "status": "missing",
            "reason": target_result.get("reason") or "target_metrics_missing",
            "best_model": None,
            "test_metrics": {},
            "issues": ["target metrics are missing or not successful"],
        }

    models = target_result.get("models") or {}
    best_name, best_payload = choose_best_regression_model(models)
    test_metrics = ((best_payload or {}).get("metrics") or {}).get("test") or {}
    floor = TARGET_METRIC_SPECS[target]["promotion_floor"]
    issues = []
    directional_accuracy = safe_float(test_metrics.get("directional_accuracy"))
    downside_rate = safe_float(test_metrics.get("downside_underestimation_rate"))
    if "directional_accuracy" in floor:
        if directional_accuracy is None:
            issues.append("test directional accuracy is missing")
        elif directional_accuracy < floor["directional_accuracy"]:
            issues.append(
                f"test directional accuracy {directional_accuracy:.3f} is below floor {floor['directional_accuracy']:.3f}"
            )
    max_downside = floor.get("max_downside_underestimation_rate")
    if max_downside is not None:
        if downside_rate is None:
            issues.append("downside underestimation rate is missing")
        elif downside_rate > max_downside:
            issues.append(
                f"downside underestimation rate {downside_rate:.3f} is above ceiling {max_downside:.3f}"
            )

    return {
        "status": "warning" if issues else "usable",
        "best_model": best_name,
        "test_metrics": test_metrics,
        "row_counts": target_result.get("row_counts", {}),
        "training_row_count_used": target_result.get("training_row_count_used"),
        "issues": issues,
    }


def choose_best_regression_model(models: dict) -> tuple[str | None, dict | None]:
    if not models:
        return None, None

    def sort_key(item):
        payload = item[1]
        metrics = (payload.get("metrics") or {}).get("test") or {}
        mae = safe_float(metrics.get("mae"))
        directional_accuracy = safe_float(metrics.get("directional_accuracy"))
        return (
            -1 if directional_accuracy is None else directional_accuracy,
            float("-inf") if mae is None else -mae,
        )

    return max(models.items(), key=sort_key)


def audit_monitoring_reports(
    *,
    monitoring_metrics: dict | None,
    calibration_report: dict | None,
    health_report: dict | None,
) -> dict:
    return {
        "metrics_warning_count": len((monitoring_metrics or {}).get("warnings") or []),
        "calibration_warning_count": len((calibration_report or {}).get("warnings") or []),
        "health_status": (health_report or {}).get("overall_status", "unknown"),
        "ml_reference_policy": (
            (health_report or {}).get("ml_reference_policy") or {}
        ).get("status", "unknown"),
        "metrics_warnings": (monitoring_metrics or {}).get("warnings") or [],
        "calibration_warnings": (calibration_report or {}).get("warnings") or [],
    }


def collect_findings(
    classification: dict,
    regression: dict,
    monitoring: dict,
) -> list[dict]:
    findings = []
    for group_name, group in [
        ("classification", classification),
        ("regression", regression),
    ]:
        for target, audit in group.items():
            for issue in audit.get("issues", []):
                findings.append(
                    {
                        "source": group_name,
                        "target": target,
                        "severity": classify_issue_severity(target, issue),
                        "message": issue,
                    }
                )
    if monitoring["metrics_warning_count"]:
        findings.append(
            {
                "source": "monitoring",
                "target": "metrics",
                "severity": "warning",
                "message": f"Monitoring metrics has {monitoring['metrics_warning_count']} warning(s).",
            }
        )
    if monitoring["calibration_warning_count"]:
        findings.append(
            {
                "source": "monitoring",
                "target": "calibration",
                "severity": "critical",
                "message": f"Calibration report has {monitoring['calibration_warning_count']} warning(s).",
            }
        )
    if monitoring["health_status"] in {"degraded", "unavailable", "unknown"}:
        findings.append(
            {
                "source": "monitoring",
                "target": "health",
                "severity": "critical" if monitoring["health_status"] == "degraded" else "warning",
                "message": f"ML health status is {monitoring['health_status']}.",
            }
        )
    return findings


def classify_issue_severity(target: str, issue: str) -> str:
    if target in {"large_drop_20d", "max_drop_20d"}:
        return "critical"
    if "downside underestimation" in issue:
        return "critical"
    return "warning"


def summarize_findings(findings: list[dict]) -> dict:
    return {
        "total": len(findings),
        "critical": sum(1 for item in findings if item["severity"] == "critical"),
        "warning": sum(1 for item in findings if item["severity"] == "warning"),
    }


def build_next_actions(findings: list[dict]) -> list[str]:
    actions = []
    messages = [finding["message"] for finding in findings]
    if any("ROC AUC" in message or "accuracy" in message for message in messages):
        actions.append("Improve classification features and candidate models before promotion.")
    if any("downside underestimation" in message for message in messages):
        actions.append("Prioritize downside risk modeling and conservative max-drop estimates.")
    if any("Calibration" in message or "calibration" in message for message in messages):
        actions.append("Add probability calibration before trusting displayed probabilities.")
    if not actions:
        actions.append("Baseline audit passed first-version floors; continue candidate comparison.")
    return dedupe(actions)


def build_baseline_audit_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 15 Baseline Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Baseline model version: `{report.get('baseline_model_version') or 'unknown'}`",
        f"- Return model version: `{report.get('return_model_version') or 'unknown'}`",
        f"- Findings: `{report['finding_summary']['total']}` total, "
        f"`{report['finding_summary']['critical']}` critical, "
        f"`{report['finding_summary']['warning']}` warning",
        "",
        "## Classification Targets",
        "",
        "| Target | Status | Best Model | Test Accuracy | Test ROC AUC | Issues |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for target, audit in report["classification_targets"].items():
        metrics = audit.get("test_metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    audit["status"],
                    str(audit.get("best_model") or "n/a"),
                    format_float(metrics.get("accuracy")),
                    format_float(metrics.get("roc_auc")),
                    "; ".join(audit.get("issues") or ["none"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Regression Targets",
            "",
            "| Target | Status | Best Model | Test MAE | Directional Accuracy | Downside Underestimation | Issues |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for target, audit in report["regression_targets"].items():
        metrics = audit.get("test_metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    audit["status"],
                    str(audit.get("best_model") or "n/a"),
                    format_float(metrics.get("mae")),
                    format_float(metrics.get("directional_accuracy")),
                    format_float(metrics.get("downside_underestimation_rate")),
                    "; ".join(audit.get("issues") or ["none"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        lines.extend(
            f"- {item['severity']} / {item['target']}: {item['message']}"
            for item in report["findings"]
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


def format_float(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.3f}"


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
