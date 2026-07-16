from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path


STATUS_PRIORITY = {
    "unknown": 0,
    "success": 1,
    "warning": 2,
    "partial_success": 3,
    "degraded": 4,
    "stale": 5,
    "missing": 6,
    "failed": 7,
}

CATEGORY_RULES = (
    (
        "supabase_schema",
        ("pgrst", "all object keys must match", "schema cache", "column", "relation does not exist"),
        "Supabase schema or payload shape does not match the write request.",
        "Compare the payload keys with the current Supabase migration and retry after fixing the mismatch.",
        False,
    ),
    (
        "supabase_connection",
        ("supabase", "postgres", "postgrest"),
        "Supabase read or write failed.",
        "Check Supabase status, secrets, request payload, and the affected table before retrying.",
        True,
    ),
    (
        "provider_unavailable",
        ("http error 429", "http error 500", "http error 502", "http error 503", "http error 504", "provider unavailable", "temporarily unavailable", "yfinance", "yahoo finance"),
        "An external market-data or news provider was unavailable or rate limited.",
        "Retry later; if the same fingerprint repeats, inspect provider limits or use the configured fallback source.",
        True,
    ),
    (
        "freshness",
        ("freshness", "stale", "trading day behind", "落後", "too old", "沒有成功執行紀錄"),
        "One or more datasets are older than the accepted freshness window.",
        "Run the matching data pipeline and verify its dependency dates before using the affected report.",
        True,
    ),
    (
        "ml_health",
        ("ml health", "model_quality", "calibration", "drift", "downside underestimation", "reduced_trust"),
        "ML monitoring found a quality, calibration, or drift warning.",
        "Keep ML Reference at reduced trust and review the generated monitoring artifact before promoting a model.",
        False,
    ),
    (
        "configuration",
        ("missing secret", "missing key", "api key", "unauthorized", "forbidden", "http 401", "http 403"),
        "A required secret, permission, or environment setting is missing or invalid.",
        "Verify GitHub Actions secrets and repository permissions; do not print secret values in logs.",
        False,
    ),
    (
        "test_failure",
        ("pytest", "assertionerror", "tests failed", "test failed"),
        "Automated tests failed.",
        "Open the test artifact, reproduce the failing test locally, and fix it on a separate branch.",
        False,
    ),
)


def load_json_sources(paths: list[str | Path]) -> list[dict]:
    sources = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["_diagnosis_source_path"] = str(path)
            sources.append(payload)
    return sources


def build_pipeline_diagnosis(
    *,
    pipeline: str,
    workflow_status: str = "unknown",
    sources: list[dict] | None = None,
    message: str | None = None,
    run_url: str | None = None,
) -> dict:
    sources = sources or []
    workflow_status = normalize_status(workflow_status)
    status = strongest_status([workflow_status, *[source_status(source) for source in sources]])
    raw_issues = collect_raw_issues(sources)
    if message and workflow_status not in {"success", "unknown"}:
        raw_issues.append({"step": pipeline, "status": workflow_status, "message": message})
    if not raw_issues and status not in {"success", "unknown"}:
        raw_issues.append(
            {
                "step": pipeline,
                "status": status,
                "message": message or "Workflow did not complete successfully and no structured log was available.",
            }
        )

    findings = [classify_issue(issue) for issue in raw_issues]
    findings = deduplicate_findings(findings)
    if status == "success" and findings:
        status = "warning"

    categories = sorted({finding["category"] for finding in findings})
    fingerprint = build_fingerprint(pipeline, categories, findings)
    severity = diagnosis_severity(status, findings)
    should_create_issue = status in {
        "failed",
        "partial_success",
        "degraded",
        "stale",
        "missing",
    }
    generated_at = datetime.now(UTC).isoformat()
    summary = build_summary(pipeline, status, findings)
    diagnosis = {
        "diagnosis_version": "pipeline_diagnosis_v1",
        "pipeline": pipeline,
        "status": status,
        "severity": severity,
        "generated_at": generated_at,
        "summary": summary,
        "categories": categories,
        "findings": findings,
        "source_paths": [source.get("_diagnosis_source_path") for source in sources if source.get("_diagnosis_source_path")],
        "run_url": run_url,
        "automation": {
            "diagnosis_mode": "rule_based",
            "llm_used": False,
            "direct_main_push_allowed": False,
        },
        "issue": {
            "should_create": should_create_issue,
            "fingerprint": fingerprint,
            "title": f"[Automation] {pipeline}: {status} ({', '.join(categories) or 'unclassified'})",
        },
    }
    diagnosis["issue"]["body"] = build_issue_body(diagnosis)
    return diagnosis


def source_status(source: dict) -> str:
    return normalize_status(
        source.get("status") or source.get("overall_status") or source.get("overall")
    )


def normalize_status(status) -> str:
    normalized = str(status or "unknown").lower()
    aliases = {
        "failure": "failed",
        "cancelled": "failed",
        "healthy": "success",
        "unavailable": "missing",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in STATUS_PRIORITY else "unknown"


def strongest_status(statuses: list[str]) -> str:
    normalized = [normalize_status(status) for status in statuses]
    return max(normalized, key=lambda status: STATUS_PRIORITY.get(status, 0), default="unknown")


def collect_raw_issues(sources: list[dict]) -> list[dict]:
    issues = []
    for source in sources:
        if source.get("recovery_version"):
            for finding in source.get("findings") or []:
                action = finding.get("recommended_action") or {}
                issues.append(
                    {
                        "step": finding.get("source", "data_recovery"),
                        "status": finding.get("status", "warning"),
                        "message": finding.get("message", "Data recovery action recommended."),
                        "recovery_action": action.get("command") or action.get("id"),
                        "retryable": action.get("safe_auto_recovery_candidate", False),
                        "affects_current_report": finding.get("affects_current_report", False),
                    }
                )
        for key in ("errors", "warnings"):
            for item in source.get(key) or []:
                issues.append(normalize_issue(item, default_status="failed" if key == "errors" else "warning"))
        for step in source.get("steps") or []:
            if step.get("status") == "failed":
                issues.append(
                    normalize_issue(
                        {
                            "step": step.get("name"),
                            "status": "failed",
                            "message": step.get("stderr_tail") or step.get("stdout_tail") or "Pipeline step failed.",
                        },
                        default_status="failed",
                    )
                )
        for component_name, component in (source.get("components") or {}).items():
            if not isinstance(component, dict) or component.get("status") in {None, "healthy", "success", "scheduled_weekly"}:
                continue
            issues.append(
                normalize_issue(
                    {
                        "step": component_name,
                        "status": component.get("status"),
                        "message": component.get("summary") or component.get("action"),
                    },
                    default_status="warning",
                )
            )
    return issues


def normalize_issue(item, *, default_status: str) -> dict:
    if isinstance(item, str):
        return {"step": "unknown", "status": default_status, "message": redact_sensitive_text(item)}
    if not isinstance(item, dict):
        return {"step": "unknown", "status": default_status, "message": redact_sensitive_text(str(item))}
    return {
        "step": str(item.get("step") or item.get("source") or item.get("component") or "unknown"),
        "status": str(item.get("status") or default_status),
        "message": redact_sensitive_text(str(item.get("message") or item.get("summary") or item)),
    }


def redact_sensitive_text(value: str) -> str:
    text = str(value)
    patterns = (
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]"),
        (r"(?i)((?:api[_-]?key|token|password|secret|gmail_app_password)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]"),
        (r"\bsk-or-v1-[A-Za-z0-9_-]+\b", "[REDACTED_OPENROUTER_KEY]"),
        (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED_JWT]"),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def classify_issue(issue: dict) -> dict:
    if issue.get("recovery_action"):
        impact = (
            "This data gap affects the current research report."
            if issue.get("affects_current_report")
            else "This is a system-maintenance gap and does not directly invalidate the current report."
        )
        return {
            **issue,
            "category": "data_recovery",
            "explanation": impact,
            "recommended_action": issue["recovery_action"],
            "retryable": bool(issue.get("retryable")),
        }
    text = f"{issue.get('step', '')} {issue.get('message', '')}".lower()
    for category, keywords, explanation, action, retryable in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return {
                **issue,
                "category": category,
                "explanation": explanation,
                "recommended_action": action,
                "retryable": retryable,
            }
    return {
        **issue,
        "category": "unknown",
        "explanation": "The failure does not match a known deterministic diagnosis rule.",
        "recommended_action": "Inspect the attached log before retrying or preparing a fix on a separate branch.",
        "retryable": False,
    }


def deduplicate_findings(findings: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for finding in findings:
        key = (finding["step"], finding["category"], finding["message"][:300])
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def build_fingerprint(pipeline: str, categories: list[str], findings: list[dict]) -> str:
    identity = {
        "pipeline": pipeline,
        "categories": categories,
        "steps": sorted({finding["step"] for finding in findings}),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def diagnosis_severity(status: str, findings: list[dict]) -> str:
    if status in {"failed", "missing", "stale"} or any(finding["status"] == "failed" for finding in findings):
        return "critical"
    if status in {"partial_success", "degraded", "warning"} or findings:
        return "warning"
    return "info"


def build_summary(pipeline: str, status: str, findings: list[dict]) -> str:
    if not findings:
        return f"{pipeline} completed with status={status}; no actionable issue was detected."
    categories = ", ".join(sorted({finding["category"] for finding in findings}))
    return f"{pipeline} completed with status={status}; {len(findings)} finding(s) classified as {categories}."


def build_issue_body(diagnosis: dict) -> str:
    marker = f"<!-- market-agent-diagnosis:{diagnosis['issue']['fingerprint']} -->"
    lines = [
        marker,
        "## Automation diagnosis",
        "",
        f"- Pipeline: `{diagnosis['pipeline']}`",
        f"- Status: `{diagnosis['status']}`",
        f"- Severity: `{diagnosis['severity']}`",
        f"- Generated: `{diagnosis['generated_at']}`",
        f"- Diagnosis mode: `rule_based`",
    ]
    if diagnosis.get("run_url"):
        lines.append(f"- GitHub run: {diagnosis['run_url']}")
    lines.extend(["", diagnosis["summary"], "", "## Findings", ""])
    for finding in diagnosis["findings"]:
        lines.extend(
            [
                f"### {finding['step']} - `{finding['category']}`",
                "",
                finding["explanation"],
                "",
                f"Observed: `{truncate(finding['message'], 500)}`",
                "",
                f"Recommended action: {finding['recommended_action']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety policy",
            "",
            "Automation may diagnose, create an issue, run tests, and prepare a PR. It must not push directly to `main`.",
        ]
    )
    return "\n".join(lines)


def render_diagnosis_markdown(diagnosis: dict) -> str:
    lines = [
        f"# Pipeline Diagnosis: {diagnosis['pipeline']}",
        "",
        f"- Status: `{diagnosis['status']}`",
        f"- Severity: `{diagnosis['severity']}`",
        f"- Generated: `{diagnosis['generated_at']}`",
        f"- Issue fingerprint: `{diagnosis['issue']['fingerprint']}`",
        f"- Create/update issue: `{str(diagnosis['issue']['should_create']).lower()}`",
        "",
        diagnosis["summary"],
        "",
        "## Findings",
        "",
    ]
    if not diagnosis["findings"]:
        lines.append("No actionable finding was detected.")
    for finding in diagnosis["findings"]:
        lines.extend(
            [
                f"### {finding['step']} - `{finding['category']}`",
                "",
                f"- Status: `{finding['status']}`",
                f"- Retryable: `{str(finding['retryable']).lower()}`",
                f"- Explanation: {finding['explanation']}",
                f"- Recommended action: {finding['recommended_action']}",
                f"- Observed: `{truncate(finding['message'], 500)}`",
                "",
            ]
        )
    return "\n".join(lines)


def truncate(value: str, max_chars: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."
