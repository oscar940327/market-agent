TRUST_LABELS = {
    "normal": "正常可參考",
    "reduced_trust": "降低信任",
    "unavailable": "暫時不可用",
}


def build_ml_reference_trust(ml_research: dict | None, ml_prediction: dict | None = None) -> dict:
    if not ml_research or ml_research.get("status") != "success":
        reason = (
            (ml_research or {}).get("reason")
            or (ml_research or {}).get("status")
            or "missing_ml_research"
        )
        return build_trust_payload(
            status="unavailable",
            reason=f"ML Reference unavailable: {reason}.",
            affected_outputs=["ml_reference"],
        )

    explicit_policy = ml_research.get("ml_reference_policy") or ml_research.get("trust_policy")
    if isinstance(explicit_policy, dict) and explicit_policy.get("status"):
        return build_trust_payload(
            status=normalize_status(explicit_policy.get("status")),
            reason=explicit_policy.get("reason") or explicit_policy.get("display_note"),
            affected_outputs=explicit_policy.get("affected_outputs") or [],
        )

    targets = ml_research.get("targets", {})
    source = ml_research.get("source") or {}
    affected_outputs = []
    reasons = []

    up_20d_quality = get_signal_quality(targets.get("up_20d"))
    large_drop_quality = get_signal_quality(targets.get("large_drop_20d"))
    return_model_quality = summarize_return_model_quality(ml_research.get("return_model"))

    if up_20d_quality in {"low", "unknown"}:
        affected_outputs.append("20_day_upside_probability")
        reasons.append(f"20-day upside signal quality is {up_20d_quality}.")

    if large_drop_quality in {"low", "low_to_medium", "unknown"}:
        affected_outputs.append("20_day_large_drop_risk")
        reasons.append(f"20-day large-drop risk signal quality is {large_drop_quality}.")

    if return_model_quality in {"low", "low_to_medium", "unknown"}:
        affected_outputs.append("return_model")
        reasons.append(f"Return model quality is {return_model_quality}.")

    if source.get("prediction_freshness") == "warning":
        affected_outputs.append("saved_prediction_freshness")
        reasons.append("Saved daily prediction freshness is warning.")

    if ml_prediction and ml_prediction.get("prediction_freshness") == "warning":
        affected_outputs.append("saved_prediction_freshness")
        reasons.append("Saved prediction row freshness is warning.")

    if affected_outputs:
        affected_outputs.append("probability_values")
        return build_trust_payload(
            status="reduced_trust",
            reason=" ".join(dedupe(reasons)),
            affected_outputs=dedupe(affected_outputs),
        )

    return build_trust_payload(
        status="normal",
        reason="ML Reference outputs have no local trust downgrade flags.",
        affected_outputs=[],
    )


def build_trust_payload(*, status: str, reason: str | None, affected_outputs: list[str]) -> dict:
    status = normalize_status(status)
    return {
        "status": status,
        "label": TRUST_LABELS.get(status, status),
        "reason": reason or "No additional reason provided.",
        "display_note": build_display_note(status),
        "affected_outputs": affected_outputs,
    }


def normalize_status(status: str | None) -> str:
    if status in {"normal", "reduced_trust", "unavailable"}:
        return status
    if status in {"warning", "degraded"}:
        return "reduced_trust"
    return "unavailable" if status in {"unknown", "failed"} else "normal"


def build_display_note(status: str) -> str:
    if status == "normal":
        return "ML Reference 可正常作為輔助參考。"
    if status == "reduced_trust":
        return "ML Reference 可以參考，但目前模型健康狀態或訊號品質需要保守看待。"
    return "ML Reference 暫時不可用，本次不應作為判斷依據。"


def get_signal_quality(target: dict | None) -> str:
    if not target:
        return "unknown"
    return target.get("signal_quality") or "unknown"


def summarize_return_model_quality(return_model: dict | None) -> str:
    if not return_model or return_model.get("status") != "success":
        return "unknown"

    qualities = [
        (target or {}).get("model_quality", "unknown")
        for target in (return_model.get("targets") or {}).values()
    ]
    if not qualities:
        return "unknown"
    if any(quality == "low" for quality in qualities):
        return "low"
    if any(quality == "low_to_medium" for quality in qualities):
        return "low_to_medium"
    if all(quality == "high" for quality in qualities):
        return "high"
    if any(quality == "medium" for quality in qualities):
        return "medium"
    return "unknown"


def dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
