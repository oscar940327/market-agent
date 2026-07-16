from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEP28_POLICY_PATH = (
    PROJECT_ROOT
    / "data"
    / "ml"
    / "model_reports"
    / "step28_model_quality_upgrade_v1.json"
)
STEP20_POLICY_PATH = (
    PROJECT_ROOT
    / "data"
    / "ml"
    / "model_reports"
    / "step20_improvement_summary_v1.json"
)


@lru_cache(maxsize=1)
def load_current_ml_model_policy() -> dict:
    step28_report = load_json_report(STEP28_POLICY_PATH)
    if step28_report:
        return build_step28_policy(step28_report)

    step20_report = load_json_report(STEP20_POLICY_PATH)
    if step20_report:
        return build_step20_policy(step20_report)
    return unavailable_policy()


def load_json_report(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_step28_policy(report: dict) -> dict:
    promotion = report.get("promotion") or {}
    targets = report.get("targets") or {}
    target_quality = {
        target: {
            "candidate": result.get("best_candidate"),
            "quality": (result.get("quality") or {}).get("level", "unknown"),
            "promotion_decision": result.get("promotion_decision", "reject"),
            "failed_checks": (result.get("quality") or {}).get("failed_checks") or [],
        }
        for target, result in targets.items()
    }
    passed_targets = promotion.get("passed_targets") or []
    blocked_targets = promotion.get("blocked_targets") or []
    return {
        "status": report.get("ml_reference_policy", "reduced_trust"),
        "model_version": "baseline_v1",
        "source": report.get("report_version", "step28_model_quality_upgrade_v1"),
        "generated_at": report.get("policy_reevaluated_at") or report.get("generated_at"),
        "candidate_promoted": promotion.get("status") == "candidate_bundle_ready",
        "downside_overlay_enabled": "max_drop_20d" in blocked_targets,
        "target_quality": target_quality,
        "passed_targets": passed_targets,
        "blocked_targets": blocked_targets,
        "key_findings": build_step28_findings(target_quality),
        "reason": promotion.get("action")
        or "Step 28 candidate bundle did not pass promotion policy.",
    }


def build_step28_findings(target_quality: dict) -> list[str]:
    findings = []
    for target, result in target_quality.items():
        if result["promotion_decision"] == "pass":
            findings.append(
                f"{target} candidate passed with {result['quality']} quality, "
                "but bundle promotion still requires all core targets."
            )
        else:
            failed = ", ".join(result["failed_checks"]) or "promotion policy"
            findings.append(f"{target} remains blocked by: {failed}.")
    return findings


def build_step20_policy(report: dict) -> dict:
    context = report.get("model_health_context") or {}
    decisions = report.get("decisions") or {}
    recommendation = report.get("final_recommendation") or {}
    return {
        "status": decisions.get("ml_reference_policy", "unknown"),
        "model_version": "baseline_v1",
        "source": report.get("report_version", "step20_improvement_summary_v1"),
        "generated_at": report.get("generated_at"),
        "computed_outcomes": context.get("computed_outcomes"),
        "calibration_findings": context.get("calibration_findings", 0),
        "error_findings": context.get("error_findings", 0),
        "candidate_promoted": decisions.get("promote_candidate_model") == "yes",
        "downside_overlay_enabled": decisions.get("use_downside_risk_overlay") == "yes",
        "key_findings": report.get("key_findings") or [],
        "reason": recommendation.get("message") or "",
    }


def unavailable_policy() -> dict:
    return {
        "status": "unknown",
        "model_version": "baseline_v1",
        "source": "model_policy_unavailable",
        "reason": "目前沒有可讀取的版本化模型政策。",
    }


def policy_applies_to_ml_research(policy: dict, ml_research: dict) -> bool:
    policy_model = policy.get("model_version")
    model_version = ml_research.get("model_version") or (
        ml_research.get("source") or {}
    ).get("model_version")
    return not model_version or not policy_model or model_version == policy_model
