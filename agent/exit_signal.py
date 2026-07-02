from __future__ import annotations

from typing import Any


EXIT_SIGNAL_ORDER = {
    "hold": 0,
    "watch": 1,
    "reduce": 2,
    "exit": 3,
}


def build_exit_signal(
    *,
    technical: dict,
    signals: dict | None = None,
    ml_research: dict | None = None,
) -> dict:
    signals = signals or {}
    current_price = safe_float(technical.get("current_price"))
    ma20 = safe_float(technical.get("ma20"))
    ma50 = safe_float(technical.get("ma50"))
    rsi14 = safe_float(technical.get("rsi14"))
    macd_histogram = safe_float(technical.get("macd_histogram"))
    momentum_state = technical.get("momentum_state")
    short_term_trend = technical.get("short_term_trend")
    large_drop = extract_large_drop_reference(ml_research)

    reasons = []
    risk_flags = []
    signal = "hold"

    if current_price is None or ma20 is None or ma50 is None:
        return {
            "status": "insufficient_data",
            "exit_signal": "watch",
            "weakening_signal_20d": "unknown",
            "email_alert_eligible": False,
            "reason": "價格或均線資料不足，無法完整判斷持有風險。",
            "reasons": ["價格或均線資料不足。"],
            "risk_flags": ["insufficient_technical_data"],
            "action_note": "先補齊技術資料，不應把這個訊號當成出場依據。",
            "ml_reference_used": False,
        }

    if current_price < ma50:
        signal = escalate(signal, "exit")
        reasons.append("價格已跌破 MA50，代表中期趨勢防線轉弱。")
        risk_flags.append("below_ma50")
    elif current_price < ma20:
        signal = escalate(signal, "watch")
        reasons.append("價格跌破 MA20，短線支撐需要觀察。")
        risk_flags.append("below_ma20")
        if macd_histogram is not None and macd_histogram < 0:
            signal = escalate(signal, "reduce")
            reasons.append("價格跌破 MA20，且 MACD histogram 為負，轉弱訊號更明確。")
            risk_flags.append("below_ma20_with_negative_macd")
    elif is_near_ma20(current_price, ma20):
        signal = escalate(signal, "watch")
        reasons.append("價格接近 MA20，適合觀察支撐是否守住。")
        risk_flags.append("near_ma20")

    if short_term_trend == "weak":
        signal = escalate(signal, "reduce" if macd_histogram is not None and macd_histogram < 0 else "watch")
        reasons.append("短線均線排列偏弱。")
        risk_flags.append("weak_short_term_trend")
    elif short_term_trend == "neutral":
        signal = escalate(signal, "watch")
        reasons.append("短線趨勢不夠明確。")
        risk_flags.append("neutral_short_term_trend")

    if macd_histogram is not None and macd_histogram < 0:
        signal = escalate(signal, "watch")
        reasons.append("MACD histogram 為負，短線動能正在轉弱。")
        risk_flags.append("negative_macd_histogram")

    if momentum_state in {"bearish_momentum", "turning_negative"}:
        signal = escalate(signal, "reduce" if current_price < ma20 else "watch")
        reasons.append("RSI / MACD 動能偏弱。")
        risk_flags.append("weakening_momentum")
    elif momentum_state == "bullish_but_overbought":
        signal = escalate(signal, "watch")
        reasons.append("RSI 偏高，短線可能有過熱回落風險。")
        risk_flags.append("overbought_risk")

    if rsi14 is not None and rsi14 < 45:
        signal = escalate(signal, "watch")
        reasons.append("RSI 低於 45，買盤動能不夠強。")
        risk_flags.append("rsi_below_45")

    if large_drop["probability"] is not None:
        if large_drop["probability"] >= 0.70 and signal in {"watch", "reduce", "exit"}:
            signal = escalate(signal, "reduce")
            reasons.append("ML 參考顯示 20 個交易日內中途大跌風險偏高。")
            risk_flags.append("high_ml_large_drop_risk")
        elif large_drop["probability"] >= 0.55:
            signal = escalate(signal, "watch")
            reasons.append("ML 參考顯示 20 個交易日內中途大跌風險需要留意。")
            risk_flags.append("medium_ml_large_drop_risk")

    if not reasons:
        reasons.append("價格仍在主要短線均線上方，且尚未看到明確轉弱訊號。")

    weakening_signal = classify_weakening_signal(signal, risk_flags)
    return {
        "status": "success",
        "exit_signal": signal,
        "weakening_signal_20d": weakening_signal,
        "email_alert_eligible": signal in {"reduce", "exit"},
        "reason": build_reason(signal, weakening_signal),
        "reasons": reasons,
        "risk_flags": sorted(set(risk_flags)),
        "action_note": build_action_note(signal),
        "ml_reference_used": large_drop["probability"] is not None,
        "ml_large_drop_risk": large_drop,
    }


def escalate(current: str, candidate: str) -> str:
    if EXIT_SIGNAL_ORDER[candidate] > EXIT_SIGNAL_ORDER[current]:
        return candidate
    return current


def classify_weakening_signal(signal: str, risk_flags: list[str]) -> str:
    if signal == "exit":
        return "high"
    if signal == "reduce":
        return "high" if len(set(risk_flags)) >= 3 else "medium"
    if signal == "watch":
        return "medium" if len(set(risk_flags)) >= 2 else "low_to_medium"
    return "low"


def build_reason(signal: str, weakening_signal: str) -> str:
    labels = {
        "hold": "目前沒有明顯出場或減碼訊號。",
        "watch": "目前出現需要觀察的轉弱跡象，但尚未形成明確減碼或出場訊號。",
        "reduce": "目前出現較明確的轉弱訊號，若已持有應提高風險控管。",
        "exit": "目前出現較嚴重的轉弱訊號，若已持有應優先檢查停損與出場規劃。",
    }
    return f"{labels.get(signal, '目前訊號需要確認')} 20 日轉弱風險為 {weakening_signal}。"


def build_action_note(signal: str) -> str:
    notes = {
        "hold": "若已持有，可持續觀察 MA20、MACD histogram 與 ML large-drop risk。",
        "watch": "若已持有，先觀察 MA20 是否守住，以及 MACD / RSI 是否繼續轉弱。",
        "reduce": "若已持有，應檢查部位大小、停損位置與是否接近原本的出場計畫。",
        "exit": "若已持有，應優先檢查是否已跌破停損或關鍵趨勢防線。",
    }
    return notes.get(signal, "先確認資料完整性，再判斷是否需要調整部位。")


def is_near_ma20(current_price: float, ma20: float) -> bool:
    if ma20 == 0:
        return False
    return abs(current_price - ma20) / ma20 <= 0.03


def extract_large_drop_reference(ml_research: dict | None) -> dict:
    if not ml_research or ml_research.get("status") != "success":
        return {
            "probability": None,
            "label": "unavailable",
            "source": "ml_unavailable",
        }

    target = (ml_research.get("targets") or {}).get("large_drop_20d") or {}
    return {
        "probability": safe_float(target.get("probability")),
        "label": target.get("label") or "unknown",
        "source": ml_research.get("source", {}).get("type") or "ml_research",
    }


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
