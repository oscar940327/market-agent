from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def sync_diagnosis_issue(
    diagnosis: dict,
    *,
    repository: str,
    token: str,
    api_url: str = "https://api.github.com",
    opener=urlopen,
) -> dict:
    issue_config = diagnosis.get("issue") or {}
    if not issue_config.get("should_create"):
        return {"status": "skipped", "reason": "diagnosis_not_issue_worthy"}
    if not repository or not token:
        return {"status": "skipped", "reason": "missing_github_configuration"}

    issues = github_request(
        "GET",
        f"{api_url}/repos/{repository}/issues?state=open&per_page=100",
        token=token,
        opener=opener,
    )
    marker = f"<!-- market-agent-diagnosis:{issue_config['fingerprint']} -->"
    existing = next(
        (
            issue
            for issue in issues
            if "pull_request" not in issue and marker in str(issue.get("body") or "")
        ),
        None,
    )
    if existing:
        comment = build_occurrence_comment(diagnosis)
        github_request(
            "POST",
            f"{api_url}/repos/{repository}/issues/{existing['number']}/comments",
            token=token,
            payload={"body": comment},
            opener=opener,
        )
        return {
            "status": "updated",
            "issue_number": existing["number"],
            "issue_url": existing.get("html_url"),
        }

    created = github_request(
        "POST",
        f"{api_url}/repos/{repository}/issues",
        token=token,
        payload={"title": issue_config["title"], "body": issue_config["body"]},
        opener=opener,
    )
    return {
        "status": "created",
        "issue_number": created.get("number"),
        "issue_url": created.get("html_url"),
    }


def build_occurrence_comment(diagnosis: dict) -> str:
    lines = [
        "The same automation diagnosis occurred again.",
        "",
        f"- Time: `{datetime.now(UTC).isoformat()}`",
        f"- Status: `{diagnosis.get('status')}`",
        f"- Severity: `{diagnosis.get('severity')}`",
    ]
    if diagnosis.get("run_url"):
        lines.append(f"- GitHub run: {diagnosis['run_url']}")
    lines.extend(["", diagnosis.get("summary", "")])
    return "\n".join(lines)


def github_request(method, url, *, token, payload=None, opener=urlopen):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "market-agent-maintenance",
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed with HTTP {error.code}: {detail}") from error
