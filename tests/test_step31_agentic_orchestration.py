import json

import pytest
import agent.reporting as reporting

from agent.agentic_orchestrator import (
    build_default_plan,
    build_default_tool_registry,
    orchestrate_research,
    parse_json_object,
    validate_specialist_output,
)


class SequenceClient:
    provider = "openrouter"
    model = "test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, system_prompt, user_prompt):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return self.responses.pop(0)


def specialist(agent, *, stance="neutral", references=None, missing=None):
    return json.dumps(
        {
            "status": "success",
            "stance": stance,
            "findings": [f"{agent} finding"],
            "evidence_references": references or [],
            "confidence": "medium",
            "missing_data": missing or [],
            "requested_handoff": None,
            "reason": "Evidence-grounded test output.",
            "warnings": [],
        }
    )


def single_stock_data():
    return {
        "intent": "single_stock_analysis",
        "status": "success",
        "ticker": "MU",
        "price_source": {"provider": "test"},
        "technical_analysis": {
            "short_term_trend": "neutral",
            "momentum_state": "turning_negative",
        },
        "signals": {
            "breakout": False,
            "volume_surge": False,
            "pullback": False,
        },
        "backtest_evidence": {"status": "no_triggered_signals"},
        "fundamentals": {"status": "success", "summary": {"stance": "positive"}},
        "news_analysis": {"summary": {"total_items": 4, "sentiment": "positive"}},
        "ml_research": {"status": "success", "targets": {}},
        "ml_reference_trust": {"status": "reduced_trust"},
        "evidence_quality": {"level": "medium"},
        "data_freshness": {"overall": "fresh", "warnings": []},
        "data_recovery": {"status": "healthy"},
        "exit_signal": {"status": "success", "exit_signal": "watch"},
        "analyst_outputs": {
            "technical": {
                "status": "success",
                "stance": "negative",
                "confidence": "medium",
                "key_evidence": [
                    {"name": "trend", "value": "neutral", "source": "technical_analysis.short_term_trend"}
                ],
                "limitations": [],
                "warning_flags": ["weakening_momentum"],
            },
            "risk": {
                "status": "success",
                "stance": "mixed",
                "confidence": "medium",
                "key_evidence": [
                    {"name": "freshness", "value": "fresh", "source": "data_freshness.overall"}
                ],
                "limitations": [],
                "warning_flags": [],
            },
        },
    }


def test_default_plan_honors_unselected_dimensions():
    plan = build_default_plan(
        "single_stock",
        {
            "include_news": False,
            "include_fundamentals": False,
            "include_technicals": False,
            "include_ml": True,
        },
    )

    assert [step["agent"] for step in plan["steps"]] == ["ml", "risk"]
    assert "news" not in plan["steps"][-1]["tools"]
    assert "fundamental" not in plan["steps"][-1]["tools"]
    assert "technical" not in plan["steps"][-1]["tools"]


def test_tool_registry_enforces_agent_allowlist():
    registry = build_default_tool_registry()

    with pytest.raises(PermissionError):
        registry.invoke(agent="news", tool="fundamental", data=single_stock_data())


def test_specialist_accepts_nested_reference_from_allowed_ml_tool():
    output = json.loads(
        specialist("ml", references=["ml_reference_trust.explanation"])
    )
    output["agent"] = "ml"

    validate_specialist_output(
        output,
        agent="ml",
        available_tools={"ml_reference"},
    )


def test_specialist_rejects_reference_from_unavailable_tool():
    output = json.loads(
        specialist("ml", references=["fundamentals.metrics.forward_pe"])
    )
    output["agent"] = "ml"

    with pytest.raises(ValueError, match="Unknown evidence reference"):
        validate_specialist_output(
            output,
            agent="ml",
            available_tools={"ml_reference"},
        )


def test_risk_specialist_accepts_completed_specialist_reference():
    output = json.loads(
        specialist("risk", references=["technical.findings"])
    )
    output["agent"] = "risk"

    validate_specialist_output(
        output,
        agent="risk",
        available_tools={"specialist_outputs"},
    )


def test_theme_specialist_accepts_indexed_constituent_reference():
    output = json.loads(
        specialist("theme", references=["constituents[0].reasons"])
    )
    output["agent"] = "theme"

    validate_specialist_output(
        output,
        agent="theme",
        available_tools={"constituents"},
    )


def test_risk_specialist_accepts_recovery_alias_from_data_recovery_tool():
    output = json.loads(
        specialist("risk", references=["recovery.status"])
    )
    output["agent"] = "risk"

    validate_specialist_output(
        output,
        agent="risk",
        available_tools={"data_recovery"},
    )


def test_fixed_orchestration_returns_valid_trace_and_outputs():
    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=single_stock_data(),
        request_options={
            "include_news": False,
            "include_fundamentals": False,
            "include_technicals": True,
            "include_ml": False,
        },
        mode="fixed",
    )

    assert result["status"] == "success"
    assert result["mode_used"] == "fixed"
    assert result["fallback_used"] is False
    assert set(result["specialist_outputs"]) == {"technical", "risk"}
    assert result["safety"]["trading_allowed"] is False
    events = [item["event"] for item in result["decision_trace"]["events"]]
    assert "plan_created" in events
    assert "tool_call" in events
    assert events[-1] == "stop"


def test_llm_orchestrator_validates_plan_and_specialist_outputs():
    plan = json.dumps(
        {
            "version": "research_plan_v1",
            "reason": "Use technical and risk evidence.",
            "steps": [
                {
                    "agent": "technical",
                    "objective": "Assess momentum.",
                    "tools": ["technical", "forbidden_tool"],
                    "required": True,
                },
                {
                    "agent": "risk",
                    "objective": "Assess downside.",
                    "tools": ["technical", "evidence", "freshness"],
                    "required": True,
                },
            ],
        }
    )
    client = SequenceClient(
        [
            plan,
            specialist("technical", stance="negative", references=["technical.momentum_state"]),
            specialist("risk", stance="negative", references=["freshness.overall"]),
        ]
    )

    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=single_stock_data(),
        request_options={
            "include_news": False,
            "include_fundamentals": False,
            "include_technicals": True,
            "include_ml": False,
        },
        mode="llm",
        llm_client=client,
    )

    assert result["mode_used"] == "llm"
    assert result["plan"]["steps"][0]["tools"] == ["technical"]
    assert result["specialist_outputs"]["technical"]["findings"]
    assert len(client.calls) == 3


def test_missing_data_replans_with_additional_allowlisted_tools():
    plan = json.dumps(
        {
            "reason": "Start with current technical data.",
            "steps": [
                {
                    "agent": "technical",
                    "objective": "Assess momentum.",
                    "tools": ["technical"],
                    "required": True,
                },
                {
                    "agent": "risk",
                    "objective": "Assess risk.",
                    "tools": ["evidence", "freshness"],
                    "required": True,
                },
            ],
        }
    )
    client = SequenceClient(
        [
            plan,
            specialist(
                "technical",
                references=["technical.momentum_state"],
                missing=["historical strategy evidence"],
            ),
            specialist("technical", references=["backtest.metrics"]),
            specialist("risk", references=["evidence.level"]),
        ]
    )

    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=single_stock_data(),
        request_options={
            "include_news": False,
            "include_fundamentals": False,
            "include_technicals": True,
            "include_ml": False,
        },
        mode="llm",
        llm_client=client,
    )

    events = result["decision_trace"]["events"]
    assert any(item["event"] == "replan" for item in events)
    assert any(item["event"] == "replan_result" and item["status"] == "success" for item in events)
    assert result["specialist_outputs"]["technical"]["missing_data"] == []


def test_specialist_stance_conflict_is_forwarded_to_risk_output():
    data = single_stock_data()
    data["analyst_outputs"]["fundamental"] = {
        "status": "success",
        "stance": "positive",
        "confidence": "medium",
        "key_evidence": [
            {"name": "growth", "value": "positive", "source": "fundamentals.summary.stance"}
        ],
        "limitations": [],
        "warning_flags": [],
    }

    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=data,
        request_options={
            "include_news": False,
            "include_fundamentals": True,
            "include_technicals": True,
            "include_ml": False,
        },
        mode="fixed",
    )

    assert result["conflict_detected"] is True
    assert result["conflicting_agents"] == ["fundamental", "technical"]
    assert "specialist_stance_conflict" in result["specialist_outputs"]["risk"]["warnings"]


def test_malformed_llm_plan_falls_back_without_breaking_report_data():
    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=single_stock_data(),
        request_options={"include_technicals": True, "include_ml": False},
        mode="llm",
        llm_client=SequenceClient(["not-json"]),
    )

    assert result["status"] == "success"
    assert result["mode_used"] == "fixed_fallback"
    assert result["fallback_used"] is True
    assert result["fallback_reason"].startswith("plan_error:")


def test_llm_plan_parser_accepts_fenced_json_with_trailing_text():
    parsed = parse_json_object(
        """```json
        {"version":"research_plan_v1","reason":"test","steps":[]}
        ```
        The plan is ready.
        """
    )

    assert parsed["version"] == "research_plan_v1"
    assert parsed["steps"] == []


def test_llm_plan_parser_uses_first_object_when_model_returns_extra_json():
    parsed = parse_json_object(
        '{"version":"research_plan_v1","reason":"first","steps":[]}\n'
        '{"debug":true}'
    )

    assert parsed["reason"] == "first"


def test_missing_openrouter_client_is_explicit_fixed_fallback(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = orchestrate_research(
        kind="single_stock",
        query="MU 現在適合進場嗎",
        data=single_stock_data(),
        request_options={"include_technicals": True, "include_ml": False},
        mode="llm",
    )

    assert result["status"] == "success"
    assert result["mode_used"] == "fixed_fallback"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "orchestrator_llm_not_configured"


def test_agentic_single_stock_uses_llm_report_writer(monkeypatch):
    client = SequenceClient(["Agentic report writer output"])
    data = single_stock_data()
    data["query"] = "MU 現在適合進場嗎"
    data["agentic_orchestration"] = {"mode_used": "llm"}
    data["agentic_outputs"] = {"technical": {"findings": ["momentum weakened"]}}
    monkeypatch.setattr(reporting, "build_rule_based_report", lambda **_: "fallback")

    result = reporting._build_report_draft(
        kind="single_stock",
        data=data,
        analyst_mode="llm",
        llm_client=client,
    )

    assert result["report"] == "Agentic report writer output"
    assert result["analyst"]["mode_used"] == "llm"
    assert len(client.calls) == 1
