AGENT_OUTPUT_STATUSES = {
    "success",
    "skipped",
    "fallback",
    "partial_success",
    "unavailable",
    "failed",
}


def build_agent_output(
    *,
    agent: str,
    status: str,
    summary=None,
    payload: dict | None = None,
    warnings: list | None = None,
    errors: list | None = None,
    metadata: dict | None = None,
    fallback_used: bool = False,
    legacy_fields: dict | None = None,
) -> dict:
    normalized_status = status if status in AGENT_OUTPUT_STATUSES else "failed"
    output = {
        "agent": agent,
        "status": normalized_status,
        "summary": summary or "",
        "payload": payload or {},
        "warnings": warnings or [],
        "errors": errors or [],
        "metadata": metadata or {},
        "fallback_used": bool(fallback_used),
    }

    if legacy_fields:
        for key, value in legacy_fields.items():
            if key not in output:
                output[key] = value

    return output


def wrap_legacy_agent_output(
    output: dict,
    *,
    agent: str | None = None,
    payload_exclude_keys: set[str] | None = None,
    metadata: dict | None = None,
    fallback_used: bool = False,
) -> dict:
    excluded = payload_exclude_keys or {
        "agent",
        "status",
        "summary",
        "warnings",
        "errors",
        "metadata",
        "fallback_used",
    }
    payload = {key: value for key, value in output.items() if key not in excluded}

    return build_agent_output(
        agent=agent or output.get("agent", "unknown"),
        status=output.get("status", "success"),
        summary=output.get("summary", ""),
        payload=payload,
        warnings=output.get("warnings", []),
        errors=output.get("errors", []),
        metadata={**output.get("metadata", {}), **(metadata or {})},
        fallback_used=output.get("fallback_used", fallback_used),
        legacy_fields=output,
    )
