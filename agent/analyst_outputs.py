from __future__ import annotations


ANALYST_OUTPUT_SCHEMA_VERSION = "analyst_output_v1"
VALID_STANCES = {"positive", "negative", "neutral", "mixed", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low", "none"}


def build_single_stock_analyst_outputs(
    *,
    technical: dict,
    signals: dict,
    fundamentals: dict,
    news_analysis: dict,
    ml_research: dict,
    ml_reference_trust: dict,
    evidence_quality: dict,
    exit_signal: dict,
    data_freshness: dict,
) -> dict:
    outputs = {
        "technical": build_technical_analyst_output(technical, signals),
        "fundamental": build_fundamental_analyst_output(fundamentals),
        "news": build_news_analyst_output(news_analysis),
        "ml": build_ml_analyst_output(ml_research, ml_reference_trust),
        "risk": build_risk_analyst_output(
            evidence_quality=evidence_quality,
            exit_signal=exit_signal,
            data_freshness=data_freshness,
            ml_reference_trust=ml_reference_trust,
        ),
    }
    for output in outputs.values():
        validate_analyst_output(output)
    return outputs


def aggregate_theme_analyst_outputs(results: list[dict]) -> dict:
    successful = [item for item in results if item.get("status") == "success"]
    outputs = {}
    for role in ("technical", "fundamental", "news", "ml", "risk"):
        constituent_outputs = [
            (item.get("analysis", {}).get("analyst_outputs") or {}).get(role)
            for item in successful
        ]
        constituent_outputs = [item for item in constituent_outputs if item]
        outputs[role] = _aggregate_analyst_role(
            role=role,
            outputs=constituent_outputs,
            total_count=len(results),
        )
        validate_analyst_output(outputs[role])
    return outputs


def build_analyst_consensus(outputs: dict) -> dict:
    stance_by_analyst = {
        name: output.get("stance", "unknown")
        for name, output in outputs.items()
    }
    positive = sorted(name for name, stance in stance_by_analyst.items() if stance == "positive")
    negative = sorted(name for name, stance in stance_by_analyst.items() if stance == "negative")
    mixed = sorted(name for name, stance in stance_by_analyst.items() if stance == "mixed")
    has_conflict = bool(positive and negative)
    return {
        "schema_version": ANALYST_OUTPUT_SCHEMA_VERSION,
        "stance_by_analyst": stance_by_analyst,
        "positive_analysts": positive,
        "negative_analysts": negative,
        "mixed_analysts": mixed,
        "has_conflict": has_conflict,
        "consensus": "mixed" if has_conflict or mixed else "positive" if positive else "negative" if negative else "neutral",
        "warning_flags": sorted(
            set(flag for output in outputs.values() for flag in output.get("warning_flags", []))
        ),
    }


def build_technical_analyst_output(technical: dict, signals: dict) -> dict:
    trend = technical.get("short_term_trend", "unknown")
    momentum = technical.get("momentum_state", "unknown")
    above_ma20 = technical.get("is_above_ma20")
    macd_histogram = technical.get("macd_histogram")
    macd_value = _safe_number(macd_histogram)
    triggered = [
        name
        for name, key in (
            ("breakout", "is_breakout"),
            ("volume_surge", "is_volume_surge"),
            ("pullback", "is_pullback"),
        )
        if (signals.get(name) or {}).get(key)
    ]
    positive = trend == "strong" or momentum in {"bullish_momentum", "bullish_but_overbought"}
    negative = trend == "weak" or momentum in {"bearish_momentum", "turning_negative"}
    stance = "mixed" if positive and negative else "positive" if positive else "negative" if negative else "neutral"
    warnings = []
    if above_ma20 is False:
        warnings.append("below_ma20")
    if macd_value is not None and macd_value < 0:
        warnings.append("negative_macd_histogram")
    if momentum in {"bearish_momentum", "turning_negative"}:
        warnings.append("weakening_momentum")
    return _output(
        analyst="technical_analyst",
        status="success",
        stance=stance,
        confidence="high" if triggered else "medium",
        key_evidence=[
            _evidence("short_term_trend", trend, "technical_analysis.short_term_trend"),
            _evidence("price_vs_ma20", above_ma20, "technical_analysis.is_above_ma20"),
            _evidence("rsi_14", technical.get("rsi14"), "technical_analysis.rsi14"),
            _evidence("macd_histogram", macd_histogram, "technical_analysis.macd_histogram"),
            _evidence("momentum_state", momentum, "technical_analysis.momentum_state"),
            _evidence("triggered_signals", triggered, "signals"),
        ],
        limitations=[] if triggered else ["no_triggered_strategy_signal"],
        warning_flags=warnings,
    )


def build_fundamental_analyst_output(fundamentals: dict) -> dict:
    status = fundamentals.get("status", "unavailable")
    summary = fundamentals.get("summary") or {}
    stance = _normalize_stance(summary.get("stance")) if status == "success" else "unknown"
    positives = list(summary.get("positives") or [])
    risks = list(summary.get("risks") or [])
    metrics = fundamentals.get("metrics") or {}
    limitations = []
    warnings = []
    if status != "success":
        limitations.append(f"fundamental_status:{status}")
    if fundamentals.get("provider") == "static_fallback":
        limitations.append("static_fundamental_fallback")
        warnings.append("fallback_data")
    if not metrics:
        limitations.append("fundamental_metrics_missing")
    if risks:
        warnings.append("fundamental_risks_present")
    return _output(
        analyst="fundamental_analyst",
        status=status,
        stance=stance,
        confidence="medium" if status == "success" else "none",
        key_evidence=[
            _evidence("positives", positives, "fundamentals.summary.positives"),
            _evidence("risks", risks, "fundamentals.summary.risks"),
            _evidence("forward_pe", metrics.get("forward_pe"), "fundamentals.metrics.forward_pe"),
            _evidence("revenue_growth", metrics.get("revenue_growth"), "fundamentals.metrics.revenue_growth"),
            _evidence("earnings_growth", metrics.get("earnings_growth"), "fundamentals.metrics.earnings_growth"),
        ],
        limitations=limitations,
        warning_flags=warnings,
    )


def build_news_analyst_output(news_analysis: dict) -> dict:
    summary = news_analysis.get("summary") or {}
    status = summary.get("status") or ("success" if summary.get("total_items", 0) else "no_data")
    sentiment = str(summary.get("sentiment", "neutral")).lower()
    stance = {
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
        "mixed": "mixed",
    }.get(sentiment, "unknown")
    total_items = int(summary.get("total_items") or 0)
    limitations = [] if total_items else ["no_recent_news"]
    warnings = []
    if total_items and total_items < 3:
        warnings.append("limited_news_sample")
    return _output(
        analyst="news_analyst",
        status=status,
        stance=stance,
        confidence="high" if total_items >= 10 else "medium" if total_items >= 3 else "low" if total_items else "none",
        key_evidence=[
            _evidence("sentiment", sentiment, "news_analysis.summary.sentiment"),
            _evidence("total_items", total_items, "news_analysis.summary.total_items"),
            _evidence("high_importance_count", summary.get("high_importance_count", 0), "news_analysis.summary.high_importance_count"),
            _evidence("top_topics", summary.get("top_topics", {}), "news_analysis.summary.top_topics"),
        ],
        limitations=limitations,
        warning_flags=warnings,
    )


def build_ml_analyst_output(ml_research: dict, ml_reference_trust: dict) -> dict:
    status = ml_research.get("status", "unavailable")
    targets = ml_research.get("targets") or {}
    up_20d = _probability(targets.get("up_20d"))
    large_drop = _probability(targets.get("large_drop_20d"))
    if status != "success":
        stance = "unknown"
    elif up_20d is None:
        stance = "unknown"
    elif large_drop is not None and large_drop >= 0.65:
        stance = "negative"
    elif up_20d >= 0.55:
        stance = "positive"
    elif up_20d <= 0.45:
        stance = "negative"
    else:
        stance = "neutral"
    trust_status = ml_reference_trust.get("status", "unavailable")
    limitations = list(ml_reference_trust.get("reasons") or [])
    warnings = [] if trust_status == "normal" else [f"ml_trust:{trust_status}"]
    return _output(
        analyst="ml_analyst",
        status=status,
        stance=stance,
        confidence="medium" if status == "success" and trust_status == "normal" else "low" if status == "success" else "none",
        key_evidence=[
            _evidence("up_5d_probability", _probability(targets.get("up_5d")), "ml_research.targets.up_5d"),
            _evidence("up_10d_probability", _probability(targets.get("up_10d")), "ml_research.targets.up_10d"),
            _evidence("up_20d_probability", up_20d, "ml_research.targets.up_20d"),
            _evidence("large_drop_20d_probability", large_drop, "ml_research.targets.large_drop_20d"),
            _evidence("trust_status", trust_status, "ml_reference_trust.status"),
        ],
        limitations=limitations,
        warning_flags=warnings,
    )


def build_risk_analyst_output(
    *,
    evidence_quality: dict,
    exit_signal: dict,
    data_freshness: dict,
    ml_reference_trust: dict,
) -> dict:
    exit_value = exit_signal.get("exit_signal", "watch")
    freshness = data_freshness.get("overall", "unknown")
    evidence_level = evidence_quality.get("level", "unknown")
    stance = "negative" if exit_value in {"reduce", "exit"} else "mixed" if exit_value == "watch" else "neutral"
    warnings = list(exit_signal.get("risk_flags") or [])
    if freshness != "fresh":
        warnings.append(f"data_freshness:{freshness}")
    if ml_reference_trust.get("status") not in {None, "normal", "skipped"}:
        warnings.append(f"ml_trust:{ml_reference_trust.get('status')}")
    limitations = []
    if evidence_level in {"low", "low_to_medium", "unknown", "none"}:
        limitations.append(f"evidence_quality:{evidence_level}")
    limitations.extend(
        warning.get("message", str(warning))
        for warning in data_freshness.get("warnings", [])
    )
    return _output(
        analyst="risk_analyst",
        status=exit_signal.get("status", "unavailable"),
        stance=stance,
        confidence=_normalize_confidence(evidence_level),
        key_evidence=[
            _evidence("exit_signal", exit_value, "exit_signal.exit_signal"),
            _evidence("weakening_signal_20d", exit_signal.get("weakening_signal_20d"), "exit_signal.weakening_signal_20d"),
            _evidence("evidence_quality", evidence_level, "evidence_quality.level"),
            _evidence("data_freshness", freshness, "data_freshness.overall"),
        ],
        limitations=limitations,
        warning_flags=warnings,
    )


def validate_analyst_output(output: dict) -> None:
    required = {
        "schema_version", "analyst", "status", "stance", "confidence",
        "key_evidence", "limitations", "warning_flags",
    }
    missing = required - set(output)
    if missing:
        raise ValueError(f"Analyst output is missing fields: {sorted(missing)}")
    if output["stance"] not in VALID_STANCES:
        raise ValueError(f"Unsupported analyst stance: {output['stance']}")
    if output["confidence"] not in VALID_CONFIDENCE:
        raise ValueError(f"Unsupported analyst confidence: {output['confidence']}")
    if not all(isinstance(output[field], list) for field in ("key_evidence", "limitations", "warning_flags")):
        raise ValueError("Analyst evidence, limitations, and warnings must be lists.")


def _aggregate_analyst_role(*, role: str, outputs: list[dict], total_count: int) -> dict:
    stance_counts = {
        stance: sum(output.get("stance") == stance for output in outputs)
        for stance in VALID_STANCES
    }
    positive = stance_counts["positive"]
    negative = stance_counts["negative"]
    if positive and negative:
        stance = "mixed"
    elif positive > negative:
        stance = "positive"
    elif negative > positive:
        stance = "negative"
    elif stance_counts["neutral"]:
        stance = "neutral"
    else:
        stance = "unknown"
    coverage = len(outputs) / total_count if total_count else 0
    confidence = "high" if coverage >= 0.8 and len(outputs) >= 3 else "medium" if coverage >= 0.5 else "low" if outputs else "none"
    limitations = [item for output in outputs for item in output.get("limitations", [])]
    if coverage < 1:
        limitations.append(f"constituent_coverage:{len(outputs)}/{total_count}")
    warnings = [item for output in outputs for item in output.get("warning_flags", [])]
    return _output(
        analyst=f"{role}_analyst",
        status="success" if outputs else "unavailable",
        stance=stance,
        confidence=confidence,
        key_evidence=[
            _evidence("constituent_stance_counts", stance_counts, f"results[].analysis.analyst_outputs.{role}.stance"),
            _evidence("constituent_coverage", coverage, f"results[].analysis.analyst_outputs.{role}"),
        ],
        limitations=limitations,
        warning_flags=warnings,
    )


def _output(*, analyst, status, stance, confidence, key_evidence, limitations, warning_flags):
    return {
        "schema_version": ANALYST_OUTPUT_SCHEMA_VERSION,
        "analyst": analyst,
        "status": status,
        "stance": stance,
        "confidence": confidence,
        "key_evidence": key_evidence,
        "limitations": list(dict.fromkeys(str(item) for item in limitations if item)),
        "warning_flags": list(dict.fromkeys(str(item) for item in warning_flags if item)),
    }


def _evidence(field: str, value, source: str) -> dict:
    return {"field": field, "value": value, "source": source}


def _normalize_stance(value) -> str:
    normalized = str(value or "unknown").lower()
    aliases = {"bullish": "positive", "bearish": "negative", "favorable": "positive", "unfavorable": "negative"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in VALID_STANCES else "unknown"


def _normalize_confidence(value) -> str:
    normalized = str(value or "none").lower()
    if normalized == "low_to_medium":
        return "low"
    return normalized if normalized in VALID_CONFIDENCE else "none"


def _probability(target: dict | None) -> float | None:
    if not target:
        return None
    value = target.get("probability")
    if value is None and target.get("probability_percent") is not None:
        value = target["probability_percent"] / 100
    return _safe_number(value)


def _safe_number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
