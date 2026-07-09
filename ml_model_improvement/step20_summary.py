from __future__ import annotations

from datetime import UTC, datetime


def build_step20_improvement_summary_report(
    *,
    error_analysis: dict,
    calibration_action: dict,
    candidate_model_v2: dict,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    decisions = build_decisions(
        error_analysis=error_analysis,
        calibration_action=calibration_action,
        candidate_model_v2=candidate_model_v2,
    )
    return {
        "report_version": "step20_improvement_summary_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "inputs": {
            "error_analysis_report": error_analysis.get("report_version"),
            "calibration_action_report": calibration_action.get("report_version"),
            "candidate_model_report": candidate_model_v2.get("report_version"),
        },
        "model_health_context": {
            "computed_outcomes": error_analysis.get("computed_outcomes"),
            "error_findings": len(error_analysis.get("findings") or []),
            "calibration_findings": len(calibration_action.get("findings") or []),
            "candidate_targets": len(candidate_model_v2.get("targets") or {}),
        },
        "key_findings": build_key_findings(
            error_analysis=error_analysis,
            calibration_action=calibration_action,
            candidate_model_v2=candidate_model_v2,
        ),
        "decisions": decisions,
        "final_recommendation": build_final_recommendation(decisions),
        "next_actions": build_next_actions(decisions),
    }


def build_decisions(
    *,
    error_analysis: dict,
    calibration_action: dict,
    candidate_model_v2: dict,
) -> dict:
    candidate_ready = any(
        (target.get("promotion_readiness") or {}).get("status") == "ready_for_comparison"
        for target in (candidate_model_v2.get("targets") or {}).values()
        if isinstance(target, dict)
    )
    has_downside_critical = any(
        finding.get("source") == "downside_risk"
        and finding.get("severity") == "critical"
        for finding in error_analysis.get("findings") or []
    )
    has_large_calibration_adjustment = any(
        finding.get("source") == "large_calibration_adjustment"
        for finding in calibration_action.get("findings") or []
    )
    return {
        "promote_candidate_model": "no" if not candidate_ready or has_downside_critical else "manual_review",
        "ml_reference_policy": "reduced_trust"
        if has_downside_critical or has_large_calibration_adjustment or not candidate_ready
        else "normal",
        "replace_raw_probability_with_calibrated_probability": "no"
        if has_large_calibration_adjustment
        else "manual_review",
        "use_downside_risk_overlay": "yes" if has_downside_critical else "manual_review",
        "keep_news_and_similar_cases_out_of_core_model": "yes",
    }


def build_key_findings(
    *,
    error_analysis: dict,
    calibration_action: dict,
    candidate_model_v2: dict,
) -> list[str]:
    findings = []
    horizon_20 = (error_analysis.get("horizon_summary") or {}).get("20") or {}
    if horizon_20:
        findings.append(
            "20-day up accuracy is "
            f"{format_percent(horizon_20.get('up_accuracy'))}, and downside "
            f"underestimation is {format_percent(horizon_20.get('downside_underestimation_rate'))}."
        )
    calibration_findings = calibration_action.get("findings") or []
    if calibration_findings:
        findings.append(
            f"Calibration action report has {len(calibration_findings)} finding(s), "
            "so calibrated probabilities should remain reduced-trust."
        )
    not_ready_targets = [
        target
        for target, payload in (candidate_model_v2.get("targets") or {}).items()
        if (payload.get("promotion_readiness") or {}).get("status") != "ready_for_comparison"
    ]
    if not_ready_targets:
        findings.append(
            "Candidate v2 is not ready for promotion for: "
            + ", ".join(not_ready_targets)
            + "."
        )
    return findings


def build_final_recommendation(decisions: dict) -> dict:
    if decisions["promote_candidate_model"] == "no":
        return {
            "status": "do_not_promote",
            "message": (
                "Keep baseline_v1 visible as reduced-trust ML Reference. "
                "Use downside overlay as a conservative risk layer, but do not replace "
                "raw probabilities with calibrated values yet."
            ),
        }
    return {
        "status": "manual_review_required",
        "message": "Candidate model needs manual review before any promotion.",
    }


def build_next_actions(decisions: dict) -> list[str]:
    actions = []
    if decisions["use_downside_risk_overlay"] == "yes":
        actions.append("Monitor whether downside overlay reduces max-drop underestimation in future outcomes.")
    if decisions["replace_raw_probability_with_calibrated_probability"] == "no":
        actions.append("Keep calibrated probabilities in model reports first; do not show them as primary report values yet.")
    if decisions["promote_candidate_model"] == "no":
        actions.append("Do not promote candidate v2; continue feature engineering and outcome accumulation.")
    actions.append("Re-run Step 20 after more computed outcomes mature.")
    return actions


def build_step20_improvement_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 20 ML Improvement Summary",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Final status: `{report['final_recommendation']['status']}`",
        f"- ML Reference policy: `{report['decisions']['ml_reference_policy']}`",
        f"- Computed outcomes: `{report['model_health_context'].get('computed_outcomes')}`",
        "",
        "## Key Findings",
        "",
    ]
    lines.extend(f"- {finding}" for finding in report["key_findings"])
    lines.extend(["", "## Decisions", ""])
    for key, value in report["decisions"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Final Recommendation",
            "",
            f"- {report['final_recommendation']['message']}",
            "",
            "## Next Actions",
            "",
        ]
    )
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def format_percent(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"
