SINGLE_STOCK_REQUIRED_AGENTS = ["market_data", "technical", "evidence"]
SINGLE_STOCK_OPTIONAL_AGENTS = [
    "news",
    "fundamental",
    "backtest_evidence",
    "ml_research",
    "exit_signal",
]


def build_single_stock_orchestration_summary(agent_outputs: dict) -> dict:
    failed_required_agents = [
        agent
        for agent in SINGLE_STOCK_REQUIRED_AGENTS
        if is_failed_required_agent(agent_outputs.get(agent))
    ]
    unavailable_optional_agents = [
        agent
        for agent in SINGLE_STOCK_OPTIONAL_AGENTS
        if (agent_outputs.get(agent) or {}).get("status") == "unavailable"
    ]
    failed_optional_agents = [
        agent
        for agent in SINGLE_STOCK_OPTIONAL_AGENTS
        if (agent_outputs.get(agent) or {}).get("status") == "failed"
    ]
    fallback_agents = [
        agent
        for agent, output in agent_outputs.items()
        if output.get("fallback_used") or output.get("status") == "fallback"
    ]
    warning_agents = [
        agent
        for agent, output in agent_outputs.items()
        if output.get("warnings")
    ]

    return {
        "workflow": "single_stock",
        "overall_status": "failed" if failed_required_agents else "success",
        "required_agents": SINGLE_STOCK_REQUIRED_AGENTS,
        "optional_agents": SINGLE_STOCK_OPTIONAL_AGENTS,
        "failed_required_agents": failed_required_agents,
        "unavailable_optional_agents": unavailable_optional_agents,
        "failed_optional_agents": failed_optional_agents,
        "fallback_agents": fallback_agents,
        "warning_agents": warning_agents,
        "should_alert": bool(failed_required_agents),
    }


def is_failed_required_agent(output: dict | None) -> bool:
    if not output:
        return True

    return output.get("status") in {"failed", "unavailable"}
