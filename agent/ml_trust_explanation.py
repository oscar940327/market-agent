from __future__ import annotations


EXPLANATION_LABELS = {
    "normal": "正常可參考",
    "reduced_trust": "降低信任",
    "fallback": "使用備援計算",
    "unavailable": "暫時不可用",
    "skipped": "本次未使用",
}
REASON_CATEGORY_PRIORITY = {
    "availability": 0,
    "source": 1,
    "freshness": 2,
    "calibration": 3,
    "model_health": 4,
    "signal_quality": 5,
    "downside_risk": 6,
    "model_quality": 7,
    "historical_evidence": 8,
    "model_version": 9,
}


def build_ml_trust_explanation(
    *,
    ml_research: dict | None,
    ml_prediction: dict | None,
    status: str,
    affected_outputs: list[str],
    model_policy: dict | None = None,
) -> dict:
    research = ml_research or {}
    source = research.get("source") or {}
    source_type = source.get("type") or "unknown"
    explanation_status = classify_explanation_status(
        status=status,
        ml_status=research.get("status"),
        source_type=source_type,
    )
    reasons = []
    supports = []

    if explanation_status == "skipped":
        add_item(
            reasons,
            code="ml_skipped",
            category="availability",
            message="這個 workflow 本次不使用 ML Reference，因此沒有產生 ML 預測。",
        )
    elif explanation_status == "unavailable":
        reason = research.get("reason") or source.get("reason") or "缺少可用的 ML 輸出"
        add_item(
            reasons,
            code="ml_unavailable",
            category="availability",
            message=f"ML Reference 暫時無法產生：{reason}。",
        )

    if source_type == "runtime_fallback":
        reason = source.get("reason") or "已儲存的每日 prediction 不可用"
        add_item(
            reasons,
            code="runtime_fallback",
            category="source",
            message=f"目前使用即時計算的備援結果，原因是 {reason}，穩定性低於已儲存且已檢查的新鮮 prediction。",
        )

    freshness = source.get("prediction_freshness") or (
        (ml_prediction or {}).get("prediction_freshness")
    )
    if freshness == "warning":
        add_item(
            reasons,
            code="prediction_freshness_warning",
            category="freshness",
            message="已儲存的 prediction 有新鮮度提醒，可能沒有完整反映最新市場資料。",
        )
    elif freshness == "fresh":
        add_item(
            supports,
            code="prediction_fresh",
            category="freshness",
            message="本次使用的 prediction 新鮮度為 fresh。",
        )

    targets = research.get("targets") or {}
    add_signal_quality_reason(reasons, targets, "up_20d", "20 日上漲方向")
    add_signal_quality_reason(reasons, targets, "large_drop_20d", "20 日中途大跌風險")

    return_quality = summarize_return_model_quality(research.get("return_model"))
    if return_quality in {"low", "low_to_medium", "unknown"}:
        add_item(
            reasons,
            code="return_model_quality_limited",
            category="model_quality",
            message=f"報酬模型品質為 {return_quality}，報酬數字只能視為實驗性區間參考。",
        )

    if model_policy and model_policy.get("status") == "reduced_trust":
        add_item(
            reasons,
            code="model_health_reduced_trust",
            category="model_health",
            message="目前正式模型的整體監控尚未達到解除降低信任的標準。",
        )
        calibration_findings = int(model_policy.get("calibration_findings") or 0)
        if calibration_findings:
            add_item(
                reasons,
                code="calibration_warning",
                category="calibration",
                message=(
                    f"版本化模型政策記錄 {calibration_findings} 項校準改善事項，"
                    "預測機率與實際發生比例可能存在落差。"
                ),
            )
        if not model_policy.get("candidate_promoted", False):
            add_item(
                reasons,
                code="candidate_not_promoted",
                category="model_version",
                message="候選模型尚未通過升級條件，目前仍使用 baseline_v1。",
            )

    overlay = research.get("downside_risk_overlay") or {}
    if overlay.get("active"):
        add_item(
            reasons,
            code="downside_overlay_active",
            category="downside_risk",
            message=(
                "系統已啟用保守下跌風險修正，表示原始模型可能低估期間內的下跌幅度。"
            ),
        )

    return_reference = research.get("return_reference") or {}
    sample_size = safe_int(return_reference.get("sample_size"))
    evidence_quality = return_reference.get("evidence_quality") or "unknown"
    if sample_size >= 50:
        add_item(
            supports,
            code="historical_sample_available",
            category="historical_evidence",
            message=f"歷史相似情境有 {sample_size} 筆，證據品質為 {evidence_quality}。",
        )
    elif sample_size:
        add_item(
            reasons,
            code="historical_sample_limited",
            category="historical_evidence",
            message=f"歷史相似情境只有 {sample_size} 筆，樣本仍然有限。",
        )

    return {
        "status": explanation_status,
        "label": EXPLANATION_LABELS.get(explanation_status, explanation_status),
        "summary": build_summary(explanation_status, reasons),
        "how_to_use": build_how_to_use(explanation_status),
        "reason_codes": [item["code"] for item in reasons],
        "reasons": reasons,
        "supports": supports,
        "affected_outputs": list(dict.fromkeys(affected_outputs)),
        "source": {
            "type": source_type,
            "prediction_freshness": freshness or "unknown",
            "model_version": research.get("model_version")
            or source.get("model_version")
            or "unknown",
            "model_policy_source": (model_policy or {}).get("source"),
            "model_policy_generated_at": (model_policy or {}).get("generated_at"),
        },
    }


def classify_explanation_status(*, status: str, ml_status: str | None, source_type: str) -> str:
    if ml_status == "skipped" or source_type == "skipped":
        return "skipped"
    if status == "unavailable" or ml_status not in {None, "success"}:
        return "unavailable"
    if source_type == "runtime_fallback":
        return "fallback"
    return status


def add_signal_quality_reason(reasons: list[dict], targets: dict, key: str, label: str) -> None:
    quality = (targets.get(key) or {}).get("signal_quality") or "unknown"
    if quality in {"low", "low_to_medium", "unknown"}:
        add_item(
            reasons,
            code=f"{key}_signal_quality_{quality}",
            category="signal_quality",
            message=f"{label}的訊號品質為 {quality}，不適合單獨作為進出場依據。",
        )


def summarize_return_model_quality(return_model: dict | None) -> str:
    if not return_model or return_model.get("status") != "success":
        return "unknown"
    qualities = [
        (target or {}).get("model_quality", "unknown")
        for target in (return_model.get("targets") or {}).values()
    ]
    if not qualities:
        return "unknown"
    for quality in ("low", "low_to_medium", "unknown", "medium", "high"):
        if quality in qualities:
            return quality
    return "unknown"


def add_item(items: list[dict], *, code: str, category: str, message: str) -> None:
    if any(item["code"] == code for item in items):
        return
    items.append({"code": code, "category": category, "message": message})


def build_summary(status: str, reasons: list[dict]) -> str:
    if status == "normal":
        return "本次 ML Reference 沒有觸發信任降級條件，可作為輔助參考。"
    if status == "skipped":
        return "這個 workflow 本次不使用 ML Reference。"
    if status == "unavailable":
        return "本次沒有可用的 ML Reference，不應用它支持研究結論。"
    if status == "fallback":
        return "本次使用即時備援計算，且模型品質仍有限，相關數字需要保守解讀。"
    if reasons:
        return "本次 ML Reference 為降低信任，主要受到模型品質、校準或風險估計限制。"
    return "本次 ML Reference 需要保守解讀。"


def build_how_to_use(status: str) -> str:
    if status == "normal":
        return "可搭配技術面、基本面、新聞面與價格計畫作為輔助參考。"
    if status == "skipped":
        return "不需要解讀 ML 數字，應使用這個 workflow 原本適用的資料。"
    if status == "unavailable":
        return "忽略 ML Reference，改以其他可用證據完成判斷。"
    return "保留數字作風險與情境參考，但不可單獨改變結論、價格計畫或出場決策。"


def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def format_ml_trust_explanation_lines(explanation: dict | None) -> list[str]:
    if not explanation:
        return []

    lines = [
        f"- 信任狀態：{explanation.get('label', explanation.get('status', 'unknown'))}。",
        f"- 狀態說明：{explanation.get('summary', '目前沒有信任狀態說明。')}",
    ]
    reasons = sorted(
        explanation.get("reasons") or [],
        key=lambda item: REASON_CATEGORY_PRIORITY.get(item.get("category"), 99),
    )
    if reasons:
        lines.append(
            "- 主要原因："
            + "；".join(item["message"] for item in reasons[:4])
        )
    supports = explanation.get("supports") or []
    if supports:
        lines.append(
            "- 支持證據："
            + "；".join(item["message"] for item in supports[:2])
        )
    lines.append(f"- 使用方式：{explanation.get('how_to_use', '')}")
    return lines
