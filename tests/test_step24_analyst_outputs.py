import pytest

from agent.analyst_outputs import (
    ANALYST_OUTPUT_SCHEMA_VERSION,
    aggregate_theme_analyst_outputs,
    build_analyst_consensus,
    build_single_stock_analyst_outputs,
    validate_analyst_output,
)


def make_outputs(**overrides):
    values = {
        "technical": {
            "short_term_trend": "weak",
            "is_above_ma20": False,
            "rsi14": 45.5,
            "macd_histogram": -2.1,
            "momentum_state": "turning_negative",
        },
        "signals": {
            "breakout": {"is_breakout": False},
            "volume_surge": {"is_volume_surge": False},
            "pullback": {"is_pullback": False},
        },
        "fundamentals": {
            "status": "success",
            "provider": "supabase_fundamental_snapshots",
            "metrics": {"forward_pe": 12.0, "revenue_growth": 0.2},
            "summary": {"stance": "positive", "positives": ["growth"], "risks": []},
        },
        "news_analysis": {
            "summary": {
                "status": "success",
                "sentiment": "positive",
                "total_items": 12,
                "high_importance_count": 2,
                "top_topics": {"product_demand": 4},
            }
        },
        "ml_research": {
            "status": "success",
            "targets": {
                "up_5d": {"probability": 0.52},
                "up_10d": {"probability": 0.51},
                "up_20d": {"probability": 0.50},
                "large_drop_20d": {"probability": 0.72},
            },
        },
        "ml_reference_trust": {
            "status": "reduced_trust",
            "reasons": ["calibration warning"],
        },
        "evidence_quality": {"level": "medium"},
        "exit_signal": {
            "status": "success",
            "exit_signal": "reduce",
            "weakening_signal_20d": "high",
            "risk_flags": ["below_ma20"],
        },
        "data_freshness": {"overall": "fresh", "warnings": []},
    }
    values.update(overrides)
    return build_single_stock_analyst_outputs(**values)


def test_all_five_analysts_use_the_same_contract():
    outputs = make_outputs()
    assert set(outputs) == {"technical", "fundamental", "news", "ml", "risk"}
    contracts = [set(output) for output in outputs.values()]
    assert all(contract == contracts[0] for contract in contracts)
    assert all(output["schema_version"] == ANALYST_OUTPUT_SCHEMA_VERSION for output in outputs.values())


def test_outputs_keep_traceable_evidence_sources():
    outputs = make_outputs()
    for output in outputs.values():
        assert output["key_evidence"]
        assert all(set(item) == {"field", "value", "source"} for item in output["key_evidence"])


def test_conflicting_views_remain_independent():
    outputs = make_outputs()
    assert outputs["technical"]["stance"] == "negative"
    assert outputs["fundamental"]["stance"] == "positive"
    assert outputs["news"]["stance"] == "positive"
    assert outputs["ml"]["stance"] == "negative"
    assert outputs["risk"]["stance"] == "negative"


def test_missing_optional_data_is_explicit_not_invented():
    outputs = make_outputs(
        fundamentals={"status": "skipped", "metrics": {}, "summary": {"stance": "unknown"}},
        news_analysis={"summary": {"total_items": 0, "sentiment": "neutral"}},
    )
    assert outputs["fundamental"]["confidence"] == "none"
    assert "fundamental_metrics_missing" in outputs["fundamental"]["limitations"]
    assert outputs["news"]["confidence"] == "none"
    assert outputs["news"]["limitations"] == ["no_recent_news"]


def test_validator_rejects_nonstandard_stance():
    output = make_outputs()["technical"]
    output["stance"] = "very_bullish"
    with pytest.raises(ValueError, match="Unsupported analyst stance"):
        validate_analyst_output(output)


def test_theme_outputs_aggregate_constituent_analyst_views():
    first = make_outputs()
    second = make_outputs()
    second["technical"]["stance"] = "positive"
    results = [
        {"status": "success", "analysis": {"analyst_outputs": first}},
        {"status": "success", "analysis": {"analyst_outputs": second}},
    ]
    outputs = aggregate_theme_analyst_outputs(results)
    assert outputs["technical"]["stance"] == "mixed"
    assert outputs["technical"]["confidence"] == "medium"
    assert outputs["fundamental"]["stance"] == "positive"
    assert outputs["ml"]["stance"] == "negative"


def test_consensus_exposes_cross_analyst_conflict():
    consensus = build_analyst_consensus(make_outputs())
    assert consensus["has_conflict"] is True
    assert consensus["consensus"] == "mixed"
    assert "fundamental" in consensus["positive_analysts"]
    assert "technical" in consensus["negative_analysts"]
