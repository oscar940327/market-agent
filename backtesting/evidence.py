REQUIRED_HISTORY_YEARS = 15
MAX_LOSS_CONTROLLED = -0.08
MAX_LOSS_HIGH_RISK = -0.15


def build_backtest_evidence_quality(
    *,
    metrics: dict,
    data_window: dict,
) -> dict:
    sample_size = int(metrics.get("total_trades", 0))
    win_rate = float(metrics.get("win_rate", 0))
    average_return = float(metrics.get("average_return", 0))
    max_loss = float(metrics.get("max_loss", 0))
    history_years = float(data_window.get("history_years") or 0)
    has_required_history = bool(data_window.get("has_required_history", False))

    sample_quality = classify_sample_quality(sample_size)
    market_cycle_coverage = (
        "sufficient" if has_required_history else "insufficient"
    )
    peer_group_needed = not has_required_history
    loss_risk = classify_loss_risk(max_loss)
    level = classify_backtest_evidence_level(
        sample_size=sample_size,
        sample_quality=sample_quality,
        has_required_history=has_required_history,
        win_rate=win_rate,
        average_return=average_return,
        loss_risk=loss_risk,
    )

    return {
        "level": level,
        "stock_specific": "medium" if has_required_history else "low_to_medium",
        "backtest_sample": sample_quality,
        "data_completeness": "high" if has_required_history else "low_to_medium",
        "signal_clarity": "not_applicable",
        "news_coverage": "not_applicable",
        "social_coverage": "not_used",
        "sentiment_confidence": "not_applicable",
        "news_impact_quality": "not_applicable",
        "fundamental_coverage": "not_applicable",
        "sample_size": sample_size,
        "sample_quality": sample_quality,
        "history_years": round(history_years, 2),
        "required_history_years": REQUIRED_HISTORY_YEARS,
        "market_cycle_coverage": market_cycle_coverage,
        "peer_group_needed": peer_group_needed,
        "peer_group": "not_used",
        "market_wide": "not_used",
        "win_rate": win_rate,
        "average_return": average_return,
        "max_loss": max_loss,
        "data_start_date": data_window.get("data_start_date"),
        "data_end_date": data_window.get("data_end_date"),
        "data_as_of": data_window.get("data_as_of"),
        "loss_risk": loss_risk,
        "reason": build_evidence_reason(
            level=level,
            sample_size=sample_size,
            sample_quality=sample_quality,
            has_required_history=has_required_history,
            history_years=history_years,
            win_rate=win_rate,
            average_return=average_return,
            max_loss=max_loss,
            loss_risk=loss_risk,
        ),
    }


def classify_sample_quality(sample_size: int) -> str:
    if sample_size == 0:
        return "none"

    if sample_size <= 4:
        return "very_low"

    if sample_size <= 9:
        return "low"

    if sample_size <= 29:
        return "medium"

    return "high"


def classify_loss_risk(max_loss: float) -> str:
    if max_loss >= MAX_LOSS_CONTROLLED:
        return "controlled"

    if max_loss >= MAX_LOSS_HIGH_RISK:
        return "medium"

    return "high"


def classify_backtest_evidence_level(
    *,
    sample_size: int,
    sample_quality: str,
    has_required_history: bool,
    win_rate: float,
    average_return: float,
    loss_risk: str,
) -> str:
    if sample_size == 0:
        return "none"

    if not has_required_history:
        if sample_quality in {"medium", "high"} and average_return > 0:
            return "low_to_medium"
        return "low"

    if (
        sample_quality == "high"
        and win_rate >= 0.5
        and average_return > 0
        and loss_risk == "controlled"
    ):
        return "high"

    if sample_quality in {"medium", "high"} and average_return > 0:
        return "medium"

    if sample_quality in {"low", "medium", "high"}:
        return "low_to_medium"

    return "low"


def build_evidence_reason(
    *,
    level: str,
    sample_size: int,
    sample_quality: str,
    has_required_history: bool,
    history_years: float,
    win_rate: float,
    average_return: float,
    max_loss: float,
    loss_risk: str,
) -> str:
    if sample_size == 0:
        return (
            "這段歷史資料中沒有符合條件的交易，"
            "因此無法評估這個策略的歷史品質。"
        )

    parts = [
        f"證據品質為 {level}。",
        f"本次回測樣本數為 {sample_size}，樣本品質為 {sample_quality}。",
        f"勝率為 {win_rate * 100:.2f}%，平均報酬為 {average_return * 100:.2f}%，最大虧損為 {max_loss * 100:.2f}%。",
    ]

    if not has_required_history:
        parts.append(
            f"個股自身歷史資料約 {history_years:.2f} 年，未達 15 年需求，"
            "因此不能視為完整牛熊循環驗證。後續需要同類型股票或全市場相似案例補充。"
        )

    if loss_risk == "high":
        parts.append("最大虧損偏高，即使其他數字看起來不差，也需要保守看待。")
    elif loss_risk == "medium":
        parts.append("最大虧損屬中等風險，仍需搭配停損與部位控管。")

    return " ".join(parts)
