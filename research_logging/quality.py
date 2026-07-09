POSITIVE_CONCLUSIONS = {
    "可列入觀察",
    "觀察回踩是否有效",
    "觀察回踩有效",
    "strong_breadth",
}

CAUTION_CONCLUSIONS = {
    "暫不進場",
    "等待更好價格",
    "降低進場信心",
    "weak_breadth",
}

RISK_EXIT_SIGNALS = {"reduce", "exit"}


def classify_research_outcome_quality(outcome: dict) -> dict:
    status = outcome.get("outcome_status")
    if status == "skipped":
        return build_quality("not_applicable", "skipped_workflow")
    if status != "computed":
        return build_quality("not_ready", status or "not_computed")

    conclusion = outcome.get("conclusion")
    exit_signal = outcome.get("exit_signal")
    return_pct = safe_float(outcome.get("return_pct"))
    max_drawdown_pct = safe_float(outcome.get("max_drawdown_pct"))
    stop_loss_touched = outcome.get("stop_loss_touched")

    if exit_signal in RISK_EXIT_SIGNALS:
        return classify_exit_signal_quality(
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown_pct,
            stop_loss_touched=stop_loss_touched,
        )

    if conclusion in POSITIVE_CONCLUSIONS:
        return classify_positive_conclusion_quality(
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown_pct,
            stop_loss_touched=stop_loss_touched,
        )

    if conclusion in CAUTION_CONCLUSIONS:
        return classify_caution_conclusion_quality(
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown_pct,
            stop_loss_touched=stop_loss_touched,
        )

    return build_quality("unclear", "no_quality_rule_for_conclusion")


def classify_positive_conclusion_quality(
    *,
    return_pct: float | None,
    max_drawdown_pct: float | None,
    stop_loss_touched,
) -> dict:
    if stop_loss_touched is True:
        return build_quality("poor", "positive_signal_hit_stop_loss")
    if return_pct is not None and return_pct >= 0.03:
        return build_quality("good", "positive_signal_followed_by_gain")
    if return_pct is not None and return_pct > 0:
        return build_quality("neutral_to_good", "positive_signal_slight_gain")
    if max_drawdown_pct is not None and max_drawdown_pct <= -0.05:
        return build_quality("poor", "positive_signal_had_large_drawdown")
    return build_quality("neutral", "positive_signal_not_confirmed_yet")


def classify_caution_conclusion_quality(
    *,
    return_pct: float | None,
    max_drawdown_pct: float | None,
    stop_loss_touched,
) -> dict:
    if stop_loss_touched is True:
        return build_quality("good", "caution_signal_avoided_stop_loss")
    if max_drawdown_pct is not None and max_drawdown_pct <= -0.05:
        return build_quality("good", "caution_signal_avoided_drawdown")
    if return_pct is not None and return_pct <= 0:
        return build_quality("neutral_to_good", "caution_signal_avoided_weak_return")
    if return_pct is not None and return_pct >= 0.05:
        return build_quality("poor", "caution_signal_missed_strong_gain")
    return build_quality("neutral", "caution_signal_mixed_result")


def classify_exit_signal_quality(
    *,
    return_pct: float | None,
    max_drawdown_pct: float | None,
    stop_loss_touched,
) -> dict:
    if stop_loss_touched is True:
        return build_quality("good", "exit_signal_warned_before_stop_loss")
    if max_drawdown_pct is not None and max_drawdown_pct <= -0.05:
        return build_quality("good", "exit_signal_warned_before_drawdown")
    if return_pct is not None and return_pct < 0:
        return build_quality("neutral_to_good", "exit_signal_warned_before_loss")
    if return_pct is not None and return_pct >= 0.05:
        return build_quality("poor", "exit_signal_was_too_defensive")
    return build_quality("neutral", "exit_signal_mixed_result")


def build_quality(label: str, reason: str) -> dict:
    return {"quality": label, "quality_reason": reason}


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
