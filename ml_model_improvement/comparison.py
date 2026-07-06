from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


CORE_TARGETS = ["up_5d", "up_10d", "up_20d", "large_drop_20d"]
RISK_TARGETS = {"large_drop_20d", "max_drop_20d"}


def build_model_comparison_report(
    *,
    baseline_audit: dict,
    candidate_experiment: dict,
    diagnostics_report: dict | None = None,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    target_comparisons = {
        target: compare_target(
            target=target,
            baseline_audit=baseline_audit,
            candidate_experiment=candidate_experiment,
        )
        for target in CORE_TARGETS
    }
    risk_review = build_risk_review(
        baseline_audit=baseline_audit,
        candidate_experiment=candidate_experiment,
        diagnostics_report=diagnostics_report,
    )
    promotion_policy = build_promotion_policy(target_comparisons, risk_review)
    return {
        "report_version": "step15_model_comparison_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "target_comparisons": target_comparisons,
        "risk_review": risk_review,
        "promotion_policy": promotion_policy,
        "final_recommendation": choose_final_recommendation(promotion_policy),
        "documentation_notes": build_documentation_notes(
            target_comparisons=target_comparisons,
            risk_review=risk_review,
            promotion_policy=promotion_policy,
        ),
    }


def compare_target(
    *,
    target: str,
    baseline_audit: dict,
    candidate_experiment: dict,
) -> dict:
    baseline = (baseline_audit.get("classification_targets") or {}).get(target) or {}
    candidate = (candidate_experiment.get("targets") or {}).get(target) or {}
    candidate_best = candidate.get("best_model")
    candidate_metrics = (
        ((candidate.get("models") or {}).get(candidate_best) or {})
        .get("metrics", {})
        .get("test", {})
        if candidate_best
        else {}
    )
    baseline_metrics = baseline.get("test_metrics") or {}
    static_delta = {
        "accuracy_delta": subtract(candidate_metrics.get("accuracy"), baseline_metrics.get("accuracy")),
        "roc_auc_delta": subtract(candidate_metrics.get("roc_auc"), baseline_metrics.get("roc_auc")),
        "brier_score_candidate": safe_float(candidate_metrics.get("brier_score")),
    }
    readiness = candidate.get("promotion_readiness") or {}
    blocking_reasons = []
    if candidate.get("status") != "success":
        blocking_reasons.append("candidate target experiment did not succeed")
    if readiness.get("status") != "ready_for_comparison":
        blocking_reasons.append("candidate did not pass static promotion floors")
    if target == "large_drop_20d":
        blocking_reasons.append("large-drop target still requires outcome-based hit-rate monitoring")
    return {
        "target": target,
        "baseline_best_model": baseline.get("best_model"),
        "candidate_best_model": candidate_best,
        "baseline_test_metrics": baseline_metrics,
        "candidate_test_metrics": candidate_metrics,
        "static_delta": static_delta,
        "candidate_promotion_readiness": readiness.get("status", "unknown"),
        "decision": "reject" if blocking_reasons else "candidate_for_monitoring_review",
        "blocking_reasons": blocking_reasons,
    }


def build_risk_review(
    *,
    baseline_audit: dict,
    candidate_experiment: dict,
    diagnostics_report: dict | None,
) -> dict:
    baseline_regression = baseline_audit.get("regression_targets") or {}
    candidate_large_drop = (candidate_experiment.get("targets") or {}).get("large_drop_20d") or {}
    diagnostics_warnings = (diagnostics_report or {}).get("warnings") or []
    risk_findings = []

    for target in ["forward_return_5d", "forward_return_10d", "forward_return_20d", "max_drop_20d"]:
        audit = baseline_regression.get(target) or {}
        for issue in audit.get("issues") or []:
            if "downside underestimation" in issue:
                risk_findings.append(
                    {
                        "source": "return_model",
                        "target": target,
                        "severity": "critical",
                        "message": issue,
                    }
                )

    if candidate_large_drop.get("promotion_readiness", {}).get("status") != "ready_for_comparison":
        risk_findings.append(
            {
                "source": "candidate_large_drop",
                "target": "large_drop_20d",
                "severity": "critical",
                "message": "large_drop_20d candidate is not ready for promotion.",
            }
        )

    if any(warning.get("source") == "news_coverage" for warning in diagnostics_warnings):
        risk_findings.append(
            {
                "source": "data_coverage",
                "target": "news_features",
                "severity": "warning",
                "message": "news features should remain low-trust for ML training until coverage improves.",
            }
        )
    if any(warning.get("source") == "similar_cases" for warning in diagnostics_warnings):
        risk_findings.append(
            {
                "source": "data_coverage",
                "target": "similar_cases",
                "severity": "warning",
                "message": "similar-case features should not be core model inputs yet.",
            }
        )

    return {
        "status": "not_ready" if any(item["severity"] == "critical" for item in risk_findings) else "usable",
        "risk_findings": risk_findings,
        "policy": {
            "ml_reference_trust": "reduced_trust" if risk_findings else "normal",
            "report_wording": (
                "ML Reference may be shown, but downside and probability outputs should be described as conservative reference only."
                if risk_findings
                else "ML Reference may be shown normally."
            ),
            "promotion_blocked": bool(risk_findings),
        },
    }


def build_promotion_policy(target_comparisons: dict, risk_review: dict) -> dict:
    checks = []
    for target, comparison in target_comparisons.items():
        checks.append(
            {
                "name": f"{target}_static_readiness",
                "status": "pass" if comparison["decision"] == "candidate_for_monitoring_review" else "reject",
                "message": (
                    "Candidate passed static readiness."
                    if comparison["decision"] == "candidate_for_monitoring_review"
                    else "; ".join(comparison["blocking_reasons"])
                ),
            }
        )
    checks.append(
        {
            "name": "risk_review",
            "status": "pass" if risk_review["status"] == "usable" else "reject",
            "message": risk_review["policy"]["report_wording"],
        }
    )
    recommendation = "reject" if any(check["status"] == "reject" for check in checks) else "manual_monitoring_review"
    return {
        "recommendation": recommendation,
        "checks": checks,
        "rules": [
            "Do not promote a model unless static metrics, monitoring outcomes, calibration, and risk review pass.",
            "Do not use news or similar-case features as core ML inputs until coverage improves.",
            "Do not promote a candidate that worsens downside underestimation.",
            "Manual approval is required before replacing production ML Reference.",
        ],
    }


def choose_final_recommendation(promotion_policy: dict) -> dict:
    if promotion_policy["recommendation"] == "reject":
        return {
            "status": "do_not_promote",
            "ml_reference_policy": "reduced_trust",
            "message": "Do not promote Step 15 candidate models. Keep ML Reference visible but reduced-trust.",
        }
    return {
        "status": "manual_review_required",
        "ml_reference_policy": "reduced_trust",
        "message": "Candidate models require monitoring and manual review before any promotion.",
    }


def build_documentation_notes(
    *,
    target_comparisons: dict,
    risk_review: dict,
    promotion_policy: dict,
) -> list[str]:
    notes = [
        "Step 15 introduced a model improvement framework based on target specs, baseline audit, diagnostics, candidate experiments, calibration, and promotion policy.",
        "Current candidate models should not replace production ML Reference.",
        "Research Report should keep ML Reference visible but reduced-trust until downside risk and calibration improve.",
    ]
    if risk_review["policy"]["promotion_blocked"]:
        notes.append("Downside risk remains the main blocker; max-drop and large-drop monitoring should be improved before promotion.")
    if any(
        comparison["candidate_best_model"] and "calibrated" in comparison["candidate_best_model"]
        for comparison in target_comparisons.values()
    ):
        notes.append("Calibrated variants improved some static metrics, but calibration alone was not enough for promotion.")
    if promotion_policy["recommendation"] == "reject":
        notes.append("README / model policy should clearly say the current ML model is research-only and not production-grade investment advice.")
    return notes


def build_model_comparison_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 15 Model Comparison / Promotion Review",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Final status: `{report['final_recommendation']['status']}`",
        f"- ML Reference policy: `{report['final_recommendation']['ml_reference_policy']}`",
        f"- Message: {report['final_recommendation']['message']}",
        "",
        "## Target Comparison",
        "",
        "| Target | Baseline | Candidate | Accuracy Delta | ROC AUC Delta | Decision |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for target, comparison in report["target_comparisons"].items():
        delta = comparison["static_delta"]
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    str(comparison.get("baseline_best_model") or "n/a"),
                    str(comparison.get("candidate_best_model") or "n/a"),
                    format_number(delta.get("accuracy_delta")),
                    format_number(delta.get("roc_auc_delta")),
                    comparison["decision"],
                ]
            )
            + " |"
        )

    lines.extend(["", "## Risk Review", ""])
    lines.append(f"- Status: `{report['risk_review']['status']}`")
    lines.append(f"- ML Reference trust: `{report['risk_review']['policy']['ml_reference_trust']}`")
    if report["risk_review"]["risk_findings"]:
        lines.extend(
            f"- {item['severity']} / {item['target']}: {item['message']}"
            for item in report["risk_review"]["risk_findings"]
        )
    else:
        lines.append("- No risk findings.")

    lines.extend(["", "## Promotion Policy", ""])
    lines.append(f"- Recommendation: `{report['promotion_policy']['recommendation']}`")
    lines.extend(f"- {rule}" for rule in report["promotion_policy"]["rules"])

    lines.extend(["", "## Documentation Notes", ""])
    lines.extend(f"- {note}" for note in report["documentation_notes"])
    return "\n".join(lines) + "\n"


def subtract(left: Any, right: Any) -> float | None:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 6)


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_number(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.3f}"
