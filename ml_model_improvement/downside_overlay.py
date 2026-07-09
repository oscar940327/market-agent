from __future__ import annotations

from copy import deepcopy
from typing import Any


RISK_FLOORS = {
    "low": -0.06,
    "medium": -0.08,
    "high": -0.11,
    "severe": -0.14,
}


def apply_downside_risk_overlay(ml_research: dict, feature_snapshot: dict | None) -> dict:
    if not ml_research or ml_research.get("status") != "success":
        return ml_research

    overlay = build_downside_risk_overlay(
        feature_snapshot=feature_snapshot or {},
        ml_research=ml_research,
    )
    output = deepcopy(ml_research)
    output["downside_risk_overlay"] = overlay

    if not overlay["active"]:
        return output

    max_drop_target = (
        (output.get("return_model") or {})
        .get("targets", {})
        .get("max_drop_20d")
    )
    if not isinstance(max_drop_target, dict):
        return output

    original_value = safe_float(max_drop_target.get("predicted_value"))
    conservative_value = overlay["conservative_max_drop"]
    if original_value is None or conservative_value < original_value:
        max_drop_target["raw_predicted_value"] = original_value
        max_drop_target["raw_predicted_percent"] = (
            None if original_value is None else round(original_value * 100, 1)
        )
        max_drop_target["predicted_value"] = conservative_value
        max_drop_target["predicted_percent"] = round(conservative_value * 100, 1)
        max_drop_target["overlay_applied"] = True
        max_drop_target["overlay_reason"] = overlay["summary"]
        update_predicted_range(max_drop_target, conservative_value)

    return output


def build_downside_risk_overlay(*, feature_snapshot: dict, ml_research: dict) -> dict:
    points = 0
    reasons = []

    market_snapshot = feature_snapshot.get("market_snapshot") or {}
    price_vs_ma20 = safe_float(feature_snapshot.get("price_vs_ma20"))
    macd_histogram = safe_float(feature_snapshot.get("macd_histogram"))
    volatility_20d = safe_float(feature_snapshot.get("volatility_20d"))
    risk_event_count = safe_float(feature_snapshot.get("risk_event_count_30d"))
    market_regime = str(
        market_snapshot.get("market_regime")
        or feature_snapshot.get("market_regime")
        or "unknown"
    )
    technical_state = str(market_snapshot.get("technical_state") or "unknown")
    risk_state = str(market_snapshot.get("risk_state") or "unknown")

    if price_vs_ma20 is not None and price_vs_ma20 < 0:
        points += 2
        reasons.append("price_below_ma20")
    if macd_histogram is not None and macd_histogram < 0:
        points += 2
        reasons.append("macd_histogram_negative")
    if volatility_20d is not None and volatility_20d >= 0.04:
        points += 2
        reasons.append("high_20d_volatility")
    if market_regime == "bear":
        points += 2
        reasons.append("bear_market_regime")
    elif market_regime in {"transition", "volatile"}:
        points += 1
        reasons.append(f"{market_regime}_market_regime")
    if technical_state in {"bearish", "volume_surge"}:
        points += 2
        reasons.append(f"technical_state_{technical_state}")
    elif technical_state in {"breakout", "pullback"} and macd_histogram is not None and macd_histogram < 0:
        points += 1
        reasons.append(f"technical_state_{technical_state}_with_negative_macd")
    if risk_state in {"high", "elevated"}:
        points += 1
        reasons.append(f"risk_state_{risk_state}")
    if risk_event_count is not None and risk_event_count > 0:
        points += 1
        reasons.append("recent_risk_event_news")

    risk_level = classify_overlay_risk(points)
    conservative_max_drop = RISK_FLOORS[risk_level]
    return {
        "status": "success",
        "active": risk_level in {"medium", "high", "severe"},
        "risk_level": risk_level,
        "risk_points": points,
        "conservative_max_drop": conservative_max_drop,
        "conservative_max_drop_percent": round(conservative_max_drop * 100, 1),
        "reasons": reasons,
        "summary": build_overlay_summary(risk_level, conservative_max_drop, reasons),
        "usage_policy": "conservative_reference_only",
    }


def classify_overlay_risk(points: int) -> str:
    if points >= 7:
        return "severe"
    if points >= 5:
        return "high"
    if points >= 3:
        return "medium"
    return "low"


def build_overlay_summary(risk_level: str, conservative_max_drop: float, reasons: list[str]) -> str:
    if risk_level == "low":
        return "Downside overlay is low; no conservative max-drop adjustment is needed."
    return (
        f"Downside overlay is {risk_level}; use a conservative 20-day max-drop "
        f"reference around {conservative_max_drop * 100:.1f}% because "
        f"{', '.join(reasons) if reasons else 'risk flags are elevated'}."
    )


def update_predicted_range(target: dict, conservative_value: float) -> None:
    predicted_range = target.get("predicted_range")
    if not isinstance(predicted_range, dict):
        target["predicted_range"] = {
            "low": conservative_value,
            "high": target.get("predicted_value"),
            "low_percent": round(conservative_value * 100, 1),
            "high_percent": target.get("predicted_percent"),
        }
        return

    raw_low = safe_float(predicted_range.get("low"))
    if raw_low is None or conservative_value < raw_low:
        predicted_range["raw_low"] = raw_low
        predicted_range["raw_low_percent"] = (
            None if raw_low is None else round(raw_low * 100, 1)
        )
        predicted_range["low"] = conservative_value
        predicted_range["low_percent"] = round(conservative_value * 100, 1)
        predicted_range["method"] = "downside_risk_overlay"


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
