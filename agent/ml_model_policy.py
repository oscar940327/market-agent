from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = (
    PROJECT_ROOT
    / "data"
    / "ml"
    / "model_reports"
    / "step20_improvement_summary_v1.json"
)


@lru_cache(maxsize=1)
def load_current_ml_model_policy() -> dict:
    try:
        report = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "unknown",
            "model_version": "baseline_v1",
            "source": "model_policy_unavailable",
            "reason": "目前沒有可讀取的版本化模型政策。",
        }

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


def policy_applies_to_ml_research(policy: dict, ml_research: dict) -> bool:
    policy_model = policy.get("model_version")
    model_version = ml_research.get("model_version") or (
        ml_research.get("source") or {}
    ).get("model_version")
    return not model_version or not policy_model or model_version == policy_model
