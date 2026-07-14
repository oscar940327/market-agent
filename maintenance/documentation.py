from __future__ import annotations


DOCUMENTATION_RULES = (
    (
        (".github/workflows/", ".github/actions/", "scripts/run_daily_pipeline.py", "alerts/", "maintenance/"),
        ("docs/automation_maintenance.md", "docs/data_pipeline.md", "README.md"),
        "Automation behavior changed without updating automation or pipeline documentation.",
    ),
    (
        (".env.example",),
        ("docs/deployment.md", "README.md"),
        "Environment variables changed without updating deployment documentation.",
    ),
    (
        ("supabase/migrations/",),
        ("docs/supabase_schema.md",),
        "Supabase migrations changed without updating the schema guide.",
    ),
)


def check_documentation_sync(changed_paths: list[str]) -> list[dict]:
    normalized = {path.replace("\\", "/") for path in changed_paths}
    findings = []
    for triggers, accepted_docs, message in DOCUMENTATION_RULES:
        triggered_paths = sorted(
            path for path in normalized if any(matches_prefix(path, trigger) for trigger in triggers)
        )
        if not triggered_paths:
            continue
        if any(document in normalized for document in accepted_docs):
            continue
        findings.append(
            {
                "message": message,
                "triggered_paths": triggered_paths,
                "accepted_docs": list(accepted_docs),
            }
        )
    return findings


def matches_prefix(path: str, trigger: str) -> bool:
    return path == trigger or path.startswith(trigger)
