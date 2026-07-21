from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from agent.json_parsing import parse_first_json_object
from agent.llm_analyst import OpenRouterChatClient


AGENTIC_VERSION = "agentic_orchestration_v1"
VALID_AGENTS = {"technical", "fundamental", "news", "ml", "theme", "risk"}
VALID_STATUSES = {"success", "partial_success", "unavailable", "skipped", "failed"}
VALID_CONFIDENCE = {"high", "medium", "low", "none"}

AGENT_TOOL_ALLOWLIST = {
    "technical": {"market_data", "technical", "backtest"},
    "fundamental": {"fundamental"},
    "news": {"news"},
    "ml": {"ml_reference"},
    "theme": {"theme", "constituents"},
    "risk": {
        "technical",
        "fundamental",
        "news",
        "ml_reference",
        "evidence",
        "freshness",
        "exit_signal",
        "data_recovery",
        "specialist_outputs",
    },
}

# Specialist references name fields returned by a tool, while permissions are
# granted using the tool's public name. Keep this mapping narrow so a specialist
# can cite nested evidence without gaining access to another tool.
TOOL_EVIDENCE_ROOTS = {
    "market_data": {"market_data", "price_source", "ticker"},
    "technical": {"technical", "technical_analysis", "signals"},
    "backtest": {"backtest", "backtest_evidence", "report", "metrics"},
    "fundamental": {"fundamental", "fundamentals"},
    "news": {"news", "news_analysis", "summary"},
    "ml_reference": {
        "ml_reference",
        "ml_research",
        "ml_reference_trust",
        "theme_ml_reference",
        "theme_ml_reference_trust",
    },
    "theme": {"theme", "theme_key", "theme_name", "scan_scope", "sector_summary"},
    "constituents": {"constituents", "results"},
    "evidence": {"evidence", "evidence_quality", "research_profile"},
    "freshness": {"freshness", "data_freshness"},
    "exit_signal": {"exit_signal"},
    "data_recovery": {"data_recovery"},
    "specialist_outputs": {"specialist_outputs", "analyst_outputs"},
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    read_only: bool
    handler: Callable[[dict], Any]
    timeout_seconds: int = 10
    max_retries: int = 0
    parameters: tuple[str, ...] = ("analysis_data",)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def describe_for_agent(self, agent: str) -> list[dict]:
        allowed = AGENT_TOOL_ALLOWLIST.get(agent, set())
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "read_only": spec.read_only,
                "timeout_seconds": spec.timeout_seconds,
                "max_retries": spec.max_retries,
                "write_authority": "none" if spec.read_only else "allowlisted",
            }
            for name, spec in sorted(self._tools.items())
            if name in allowed
        ]

    def invoke(self, *, agent: str, tool: str, data: dict) -> Any:
        if tool not in AGENT_TOOL_ALLOWLIST.get(agent, set()):
            raise PermissionError(f"Agent {agent} cannot use tool {tool}.")
        if tool not in self._tools:
            raise KeyError(f"Unknown tool: {tool}")
        return deepcopy(self._tools[tool].handler(data))

    def has(self, tool: str) -> bool:
        return tool in self._tools


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    specs = (
        ("market_data", "Read market-data source and current price context.", lambda d: {
            "price_source": d.get("price_source"),
            "ticker": d.get("ticker"),
        }),
        ("technical", "Read calculated technical indicators and signals.", lambda d: {
            "technical_analysis": d.get("technical_analysis"),
            "signals": d.get("signals"),
        }),
        ("backtest", "Read deterministic historical strategy evidence.", lambda d: d.get("backtest_evidence") or d.get("report")),
        ("fundamental", "Read provider-backed fundamental snapshot.", lambda d: d.get("fundamentals")),
        ("news", "Read classified news summary; raw external text is excluded.", lambda d: {
            "summary": (d.get("news_analysis") or {}).get("summary", {}),
        }),
        ("ml_reference", "Read ML predictions, trust policy, and return references.", lambda d: {
            "ml_research": d.get("ml_research") or d.get("theme_ml_reference"),
            "ml_reference_trust": d.get("ml_reference_trust") or d.get("theme_ml_reference_trust"),
        }),
        ("theme", "Read theme breadth and aggregate evidence.", lambda d: {
            "theme_key": d.get("theme_key"),
            "theme_name": d.get("theme_name"),
            "scan_scope": d.get("scan_scope"),
            "sector_summary": d.get("sector_summary"),
        }),
        ("constituents", "Read summarized theme constituent results.", lambda d: [
            {
                "ticker": item.get("ticker"),
                "status": item.get("status"),
                "score": item.get("score"),
                "reasons": item.get("reasons"),
            }
            for item in (d.get("results") or [])[:20]
        ]),
        ("evidence", "Read evidence-quality assessment.", lambda d: d.get("evidence_quality")),
        ("freshness", "Read freshness and warning state.", lambda d: d.get("data_freshness")),
        ("exit_signal", "Read deterministic holding-risk and exit observation.", lambda d: d.get("exit_signal")),
        ("data_recovery", "Read diagnosed data gaps and recovery recommendations.", lambda d: d.get("data_recovery")),
        ("specialist_outputs", "Read validated outputs from completed specialists.", lambda d: d.get("_agentic_outputs", {})),
    )
    for name, description, handler in specs:
        registry.register(
            ToolSpec(
                name=name,
                description=description,
                read_only=True,
                handler=handler,
            )
        )
    return registry


def orchestrate_research(
    *,
    kind: str,
    query: str,
    data: dict,
    request_options: dict | None = None,
    mode: str | None = None,
    llm_client=None,
    tool_registry: ToolRegistry | None = None,
) -> dict:
    requested_mode = normalize_agentic_mode(
        mode or os.getenv("MARKET_AGENT_ORCHESTRATOR_MODE", "fixed")
    )
    options = normalize_request_options(kind, request_options)
    registry = tool_registry or build_default_tool_registry()
    run_id = str(uuid4())
    trace = build_trace(run_id, kind, query, requested_mode, options)

    if data.get("status") != "success":
        trace_event(trace, "stop", status="skipped", reason="workflow_not_successful")
        return build_orchestration_result(
            trace=trace,
            requested_mode=requested_mode,
            mode_used="fixed",
            status="skipped",
            plan=build_default_plan(kind, options),
            outputs={},
            fallback_used=False,
            fallback_reason="workflow_not_successful",
        )

    client = llm_client or get_orchestrator_client_from_env()
    if client is not None and not hasattr(client, "_agentic_base_model"):
        client._agentic_base_model = getattr(client, "model", None)
    use_llm = requested_mode == "llm" and client is not None
    fallback_reason = None
    if requested_mode == "llm" and client is None:
        fallback_reason = "orchestrator_llm_not_configured"
        trace_event(trace, "fallback", stage="client", reason=fallback_reason)

    try:
        plan = (
            build_llm_plan(kind, query, options, registry, client, trace)
            if use_llm
            else build_default_plan(kind, options)
        )
    except Exception as error:
        plan = build_default_plan(kind, options)
        fallback_reason = f"plan_error:{error}"
        trace_event(trace, "fallback", stage="plan", reason=fallback_reason)

    if not use_llm:
        trace_event(trace, "plan_created", mode="fixed", reason=plan["reason"], steps=plan["steps"])

    outputs = {}
    max_steps = get_int_env("MARKET_AGENT_ORCHESTRATOR_MAX_STEPS", 8, minimum=1, maximum=20)
    max_replans = get_int_env("MARKET_AGENT_ORCHESTRATOR_MAX_REPLANS", 2, minimum=0, maximum=5)
    replan_count = 0

    for step in plan["steps"][:max_steps]:
        agent = step["agent"]
        trace_event(trace, "agent_start", agent=agent, tools=step["tools"])
        try:
            tool_payload = invoke_agent_tools(
                registry=registry,
                agent=agent,
                tools=step["tools"],
                data={**data, "_agentic_outputs": outputs},
                trace=trace,
            )
            output = run_specialist_agent(
                agent=agent,
                objective=step["objective"],
                query=query,
                tool_payload=tool_payload,
                data=data,
                use_llm=use_llm,
                llm_client=client,
            )
            if use_llm:
                trace_event(
                    trace,
                    "llm_call",
                    role=agent,
                    provider=getattr(client, "provider", None),
                    model=getattr(client, "model", None),
                    usage="not_returned_by_client",
                )
            validate_specialist_output(output, agent=agent, available_tools=set(tool_payload))
        except Exception as error:
            output = build_deterministic_specialist_output(agent, data, str(error))
            fallback_reason = fallback_reason or f"agent_error:{agent}:{error}"
            trace_event(trace, "fallback", stage="agent", agent=agent, reason=str(error))
        outputs[agent] = output
        trace_event(
            trace,
            "agent_finish",
            agent=agent,
            status=output["status"],
            confidence=output["confidence"],
            missing_data=output["missing_data"],
        )

        if output["missing_data"] and replan_count < max_replans:
            replan_count += 1
            unused_tools = [
                tool
                for tool in sorted(AGENT_TOOL_ALLOWLIST.get(agent, set()))
                if tool not in step["tools"] and registry.has(tool)
            ]
            trace_event(
                trace,
                "replan",
                agent=agent,
                reason="missing_data",
                missing_data=output["missing_data"],
                additional_tools=unused_tools,
                result="additional_tools_selected" if unused_tools else "no_additional_allowlisted_tool",
            )
            if unused_tools:
                try:
                    recovered_payload = {
                        **tool_payload,
                        **invoke_agent_tools(
                            registry=registry,
                            agent=agent,
                            tools=unused_tools,
                            data={**data, "_agentic_outputs": outputs},
                            trace=trace,
                        ),
                    }
                    recovered = run_specialist_agent(
                        agent=agent,
                        objective=f"{step['objective']} Reassess after allowed data recovery.",
                        query=query,
                        tool_payload=recovered_payload,
                        data=data,
                        use_llm=use_llm,
                        llm_client=client,
                    )
                    if use_llm:
                        trace_event(
                            trace,
                            "llm_call",
                            role=agent,
                            purpose="replan",
                            provider=getattr(client, "provider", None),
                            model=getattr(client, "model", None),
                            usage="not_returned_by_client",
                        )
                    validate_specialist_output(
                        recovered,
                        agent=agent,
                        available_tools=set(recovered_payload),
                    )
                    outputs[agent] = recovered
                    output = recovered
                    trace_event(
                        trace,
                        "replan_result",
                        agent=agent,
                        status=recovered["status"],
                        missing_data=recovered["missing_data"],
                    )
                except Exception as error:
                    trace_event(trace, "replan_result", agent=agent, status="failed", reason=str(error))

    conflict = detect_stance_conflict(outputs)
    if conflict:
        trace_event(trace, "conflict_detected", agents=conflict)
        if "risk" in outputs:
            outputs["risk"]["warnings"] = sorted(
                set(outputs["risk"].get("warnings", []) + ["specialist_stance_conflict"])
            )
    trace_event(
        trace,
        "stop",
        status="success",
        reason="plan_completed",
        executed_steps=len(outputs),
        replan_count=replan_count,
    )
    trace["finished_at"] = datetime.now(timezone.utc).isoformat()
    return build_orchestration_result(
        trace=trace,
        requested_mode=requested_mode,
        mode_used="llm" if use_llm and fallback_reason is None else "fixed_fallback" if fallback_reason else "fixed",
        status="success",
        plan=plan,
        outputs=outputs,
        fallback_used=bool(fallback_reason),
        fallback_reason=fallback_reason,
        conflict=conflict,
    )


def build_default_plan(kind: str, options: dict) -> dict:
    agents = []
    if kind == "theme":
        agents.append(("theme", ["theme", "constituents"], "Assess theme breadth and constituent consistency."))
    elif kind == "backtest":
        agents.append(("technical", ["market_data", "backtest"], "Interpret deterministic strategy evidence and its limitations."))
    else:
        if options["include_technicals"]:
            agents.append(("technical", ["market_data", "technical", "backtest"], "Assess trend, momentum, and triggered technical evidence."))
        if options["include_fundamentals"]:
            agents.append(("fundamental", ["fundamental"], "Assess business and valuation evidence."))
        if options["include_news"]:
            agents.append(("news", ["news"], "Assess recent news relevance, impact, and limitations."))
        if options["include_ml"]:
            agents.append(("ml", ["ml_reference"], "Interpret ML reference numbers and trust policy conservatively."))
    agents.append(("risk", allowed_risk_tools(options, kind), "Integrate specialist conflicts, downside, data, and holding-risk evidence."))
    return {
        "version": "research_plan_v1",
        "reason": "Conservative deterministic plan constrained by request scope.",
        "steps": [
            {"agent": agent, "objective": objective, "tools": tools, "required": agent == "risk"}
            for agent, tools, objective in agents
        ],
    }


def build_llm_plan(kind, query, options, registry, client, trace) -> dict:
    default_plan = build_default_plan(kind, options)
    allowed_agents = [step["agent"] for step in default_plan["steps"]]
    tool_map = {agent: registry.describe_for_agent(agent) for agent in allowed_agents}
    prompt = {
        "kind": kind,
        "query": query,
        "request_scope": options,
        "allowed_agents": allowed_agents,
        "allowed_tools": tool_map,
        "requirements": [
            "Selected research dimensions are mandatory; unselected dimensions are prohibited.",
            "Risk checks are always allowed.",
            "Return JSON only with version, reason, and steps.",
            "Each step requires agent, objective, tools, and required.",
        ],
    }
    raw = client.generate(
        "You are a constrained financial research orchestrator. Plan only from the allowlists. Do not calculate or invent financial values.",
        json.dumps(prompt, ensure_ascii=False, default=str),
    )
    trace_event(
        trace,
        "llm_call",
        role="research_orchestrator",
        provider=getattr(client, "provider", None),
        model=getattr(client, "model", None),
        usage="not_returned_by_client",
    )
    value = parse_json_object(raw)
    plan = validate_plan(value, default_plan, options, kind)
    trace_event(trace, "plan_created", mode="llm", reason=plan["reason"], steps=plan["steps"])
    return plan


def validate_plan(value: dict, default_plan: dict, options: dict, kind: str) -> dict:
    allowed_defaults = {step["agent"]: step for step in default_plan["steps"]}
    steps = []
    seen = set()
    for raw_step in value.get("steps") or []:
        agent = str(raw_step.get("agent", "")).strip().lower()
        if agent not in allowed_defaults or agent in seen:
            continue
        requested_tools = [str(item) for item in raw_step.get("tools") or []]
        allowed_tools = set(allowed_defaults[agent]["tools"])
        tools = [tool for tool in requested_tools if tool in allowed_tools]
        if not tools:
            tools = list(allowed_defaults[agent]["tools"])
        steps.append({
            "agent": agent,
            "objective": str(raw_step.get("objective") or allowed_defaults[agent]["objective"]),
            "tools": tools,
            "required": bool(raw_step.get("required", agent == "risk")),
        })
        seen.add(agent)
    for agent, default_step in allowed_defaults.items():
        if agent not in seen and (default_step["required"] or agent != "risk"):
            steps.append(default_step)
    if "risk" not in {step["agent"] for step in steps}:
        steps.append(allowed_defaults["risk"])
    return {
        "version": "research_plan_v1",
        "reason": str(value.get("reason") or "LLM plan validated against request scope."),
        "steps": steps,
    }


def invoke_agent_tools(*, registry, agent, tools, data, trace) -> dict:
    payload = {}
    for tool in tools:
        result = registry.invoke(agent=agent, tool=tool, data=data)
        payload[tool] = result
        trace_event(trace, "tool_call", agent=agent, tool=tool, status="success")
    return payload


def run_specialist_agent(*, agent, objective, query, tool_payload, data, use_llm, llm_client):
    if not use_llm:
        return build_deterministic_specialist_output(agent, data)
    configure_specialist_model(llm_client, agent)
    prompt = {
        "role": agent,
        "objective": objective,
        "query": query,
        "tool_results": tool_payload,
        "output_schema": {
            "status": "success|partial_success|unavailable",
            "stance": "positive|negative|neutral|mixed|unknown",
            "findings": ["short evidence-grounded finding"],
            "evidence_references": ["tool_name.path"],
            "confidence": "high|medium|low|none",
            "missing_data": ["missing field"],
            "requested_handoff": None,
            "reason": "short rationale",
            "warnings": ["warning"],
        },
    }
    raw = llm_client.generate(
        "You are a read-only specialist analyst. Use only supplied tool results. Never invent or recalculate financial numbers. Return one JSON object only.",
        json.dumps(prompt, ensure_ascii=False, default=str),
    )
    output = parse_json_object(raw)
    output["agent"] = agent
    output["schema_version"] = "specialist_output_v1"
    return output


def build_deterministic_specialist_output(agent: str, data: dict, warning: str | None = None) -> dict:
    source = (data.get("analyst_outputs") or {}).get(agent) or {}
    evidence = source.get("key_evidence") or []
    findings = [
        f"{item.get('name')}: {item.get('value')}"
        for item in evidence[:5]
        if item.get("value") is not None
    ]
    reference_root = {
        "technical": "technical",
        "fundamental": "fundamental",
        "news": "news",
        "ml": "ml_reference",
        "risk": "evidence",
    }.get(agent, agent)
    references = [f"{reference_root}.{index}" for index, _ in enumerate(evidence[:5], start=1)]
    if agent == "theme":
        summary = data.get("sector_summary") or {}
        findings = [
            f"average_score: {summary.get('average_score')}",
            f"positive_breadth: {summary.get('positive_breadth')}",
            f"breadth_label: {summary.get('breadth_label')}",
        ]
        references = ["theme.sector_summary"]
    if agent == "risk" and not source:
        findings = [
            f"evidence_quality: {(data.get('evidence_quality') or {}).get('level')}",
            f"freshness: {(data.get('data_freshness') or {}).get('overall')}",
        ]
        references = ["evidence.level", "freshness.overall"]
    if agent == "technical" and data.get("intent") == "backtest_query":
        metrics = ((data.get("report") or {}).get("metrics") or data.get("metrics") or {})
        findings = [f"{name}: {value}" for name, value in metrics.items() if value is not None]
        references = ["backtest.metrics"]
    limitations = list(source.get("limitations") or [])
    warnings = list(source.get("warning_flags") or [])
    if warning:
        warnings.append(warning)
    return {
        "schema_version": "specialist_output_v1",
        "agent": agent,
        "status": (
            "success"
            if findings and not source.get("status")
            else normalize_specialist_status(source.get("status"))
        ),
        "stance": source.get("stance", "unknown"),
        "findings": findings,
        "evidence_references": references,
        "confidence": normalize_confidence(source.get("confidence")),
        "missing_data": limitations,
        "requested_handoff": None,
        "reason": "Deterministic fallback derived from validated structured analysis.",
        "warnings": warnings,
    }


def validate_specialist_output(output: dict, *, agent: str, available_tools: set[str]) -> None:
    if output.get("agent") != agent:
        raise ValueError("Specialist output agent mismatch.")
    if output.get("status") not in VALID_STATUSES:
        raise ValueError("Invalid specialist status.")
    if output.get("confidence") not in VALID_CONFIDENCE:
        raise ValueError("Invalid specialist confidence.")
    for key in ("findings", "evidence_references", "missing_data", "warnings"):
        if not isinstance(output.get(key), list):
            raise ValueError(f"Specialist field {key} must be a list.")
    allowed_reference_roots = set()
    for tool in available_tools:
        allowed_reference_roots.update(TOOL_EVIDENCE_ROOTS.get(tool, {tool}))
    for reference in output["evidence_references"]:
        root = str(reference).split(".", 1)[0]
        if root not in allowed_reference_roots:
            raise ValueError(f"Unknown evidence reference: {reference}")
    handoff = output.get("requested_handoff")
    if handoff not in {None, "risk"}:
        raise ValueError("Unsupported specialist handoff.")


def normalize_request_options(kind: str, options: dict | None) -> dict:
    source = options or {}
    return {
        "include_news": bool(source.get("include_news", kind in {"single_stock", "theme"})),
        "include_fundamentals": bool(source.get("include_fundamentals", kind in {"single_stock", "theme"})),
        "include_technicals": bool(source.get("include_technicals", True)),
        "include_ml": bool(source.get("include_ml", kind in {"single_stock", "theme"})),
    }


def allowed_risk_tools(options: dict, kind: str) -> list[str]:
    tools = ["evidence", "freshness", "data_recovery", "specialist_outputs"]
    if options["include_technicals"] or kind == "backtest":
        tools.extend(["technical", "exit_signal"])
    if options["include_fundamentals"]:
        tools.append("fundamental")
    if options["include_news"]:
        tools.append("news")
    if options["include_ml"]:
        tools.append("ml_reference")
    return tools


def get_orchestrator_client_from_env():
    if os.getenv("MARKET_AGENT_ORCHESTRATOR_PROVIDER", "openrouter").lower() != "openrouter":
        return None
    client = OpenRouterChatClient.from_env()
    if client is None:
        return None
    model = os.getenv("MARKET_AGENT_ORCHESTRATOR_MODEL", "").strip()
    if model:
        client.model = model
    return client


def configure_specialist_model(client, agent: str) -> None:
    env_name = f"MARKET_AGENT_{agent.upper()}_MODEL"
    model = os.getenv(env_name, "").strip()
    if hasattr(client, "model"):
        client.model = model or getattr(client, "_agentic_base_model", client.model)


def parse_json_object(raw: str) -> dict:
    return parse_first_json_object(
        raw,
        error_message="LLM response must include a JSON object.",
    )


def detect_stance_conflict(outputs: dict) -> list[str]:
    positive = [name for name, output in outputs.items() if output.get("stance") == "positive"]
    negative = [name for name, output in outputs.items() if output.get("stance") == "negative"]
    return sorted(positive + negative) if positive and negative else []


def build_trace(run_id, kind, query, requested_mode, options):
    return {
        "trace_version": "agent_decision_trace_v1",
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "query": query,
        "requested_mode": requested_mode,
        "request_scope": options,
        "events": [],
    }


def trace_event(trace: dict, event: str, **details) -> None:
    trace["events"].append({"sequence": len(trace["events"]) + 1, "event": event, **details})


def build_orchestration_result(
    *, trace, requested_mode, mode_used, status, plan, outputs,
    fallback_used, fallback_reason, conflict=None,
):
    return {
        "version": AGENTIC_VERSION,
        "status": status,
        "requested_mode": requested_mode,
        "mode_used": mode_used,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "plan": plan,
        "specialist_outputs": outputs,
        "conflict_detected": bool(conflict),
        "conflicting_agents": conflict or [],
        "decision_trace": trace,
        "limits": {
            "max_steps": get_int_env("MARKET_AGENT_ORCHESTRATOR_MAX_STEPS", 8, minimum=1, maximum=20),
            "max_replans": get_int_env("MARKET_AGENT_ORCHESTRATOR_MAX_REPLANS", 2, minimum=0, maximum=5),
        },
        "safety": {
            "read_only": True,
            "trading_allowed": False,
            "database_writes_allowed": False,
            "structured_numbers_mutable": False,
        },
    }


def normalize_agentic_mode(value: str | None) -> str:
    normalized = str(value or "fixed").strip().lower().replace("-", "_")
    return normalized if normalized in {"fixed", "llm"} else "fixed"


def normalize_specialist_status(value) -> str:
    if value in VALID_STATUSES:
        return value
    if value in {"no_data", "unknown", None}:
        return "unavailable"
    return "partial_success"


def normalize_confidence(value) -> str:
    return value if value in VALID_CONFIDENCE else "none"


def get_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
