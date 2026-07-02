import html
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - keeps GitHub failure alerts dependency-light.
    load_dotenv = None


ALERT_STATUSES = {"failed", "partial_success", "warning", "stale", "missing"}


@dataclass(frozen=True)
class AlertEmailConfig:
    enabled: bool
    provider: str
    sender: str
    recipients: tuple[str, ...]
    password: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587


def load_alert_email_config() -> AlertEmailConfig:
    if load_dotenv:
        load_dotenv()

    provider = os.getenv("ALERT_EMAIL_PROVIDER", "gmail").strip().lower()
    return AlertEmailConfig(
        enabled=parse_bool(os.getenv("ALERT_EMAIL_ENABLED", "false")),
        provider=provider,
        sender=os.getenv("ALERT_EMAIL_FROM", "").strip(),
        recipients=parse_recipients(os.getenv("ALERT_EMAIL_TO", "")),
        password=os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
        smtp_host=os.getenv("ALERT_EMAIL_SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=int(os.getenv("ALERT_EMAIL_SMTP_PORT", "587")),
    )


def parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_recipients(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def send_pipeline_alert_if_needed(
    pipeline_log: dict,
    *,
    config: AlertEmailConfig | None = None,
    smtp_factory: Callable[..., smtplib.SMTP] | None = None,
) -> dict:
    alert = build_pipeline_alert(pipeline_log)
    if not alert["should_send"]:
        return {"status": "skipped", "reason": alert["reason"], "alert": alert}
    return send_alert_email(alert, config=config, smtp_factory=smtp_factory)


def build_pipeline_alert(pipeline_log: dict) -> dict:
    status = str(pipeline_log.get("status", "unknown"))
    warnings = pipeline_log.get("warnings") or []
    errors = pipeline_log.get("errors") or []
    failed_steps = [
        step
        for step in pipeline_log.get("steps", [])
        if step.get("status") == "failed"
    ]
    should_send = status in ALERT_STATUSES or bool(warnings or errors)
    severity = classify_alert_severity(status=status, warnings=warnings, errors=errors)
    subject = f"[Market Agent] {severity.upper()} daily pipeline: {status}"
    return {
        "should_send": should_send,
        "reason": "alertable_pipeline_status" if should_send else "pipeline_success",
        "subject": subject,
        "severity": severity,
        "pipeline": pipeline_log.get("pipeline", "daily"),
        "status": status,
        "started_at": pipeline_log.get("started_at"),
        "finished_at": pipeline_log.get("finished_at"),
        "duration_seconds": pipeline_log.get("duration_seconds"),
        "summary": build_pipeline_summary(pipeline_log),
        "warnings": warnings,
        "errors": errors,
        "failed_steps": failed_steps,
        "log_path": pipeline_log.get("log_path"),
        "latest_log_path": pipeline_log.get("latest_log_path"),
        "html": build_pipeline_alert_html(pipeline_log, severity=severity),
        "text": build_pipeline_alert_text(pipeline_log),
    }


def build_github_action_alert(
    *,
    pipeline: str,
    status: str,
    message: str,
    log_path: str | None = None,
    run_url: str | None = None,
) -> dict:
    severity = classify_alert_severity(status=status, warnings=[], errors=[message])
    subject = f"[Market Agent] {severity.upper()} {pipeline}: {status}"
    alert = {
        "should_send": True,
        "reason": "github_action_failure",
        "subject": subject,
        "severity": severity,
        "pipeline": pipeline,
        "status": status,
        "summary": message,
        "warnings": [],
        "errors": [{"step": pipeline, "status": status, "message": message}],
        "failed_steps": [],
        "log_path": log_path,
        "latest_log_path": log_path,
        "run_url": run_url,
    }
    alert["html"] = build_generic_alert_html(alert)
    alert["text"] = build_generic_alert_text(alert)
    return alert


def classify_alert_severity(*, status: str, warnings: list, errors: list) -> str:
    if status in {"failed", "stale", "missing"} or errors:
        return "critical"
    if status in {"partial_success", "warning"} or warnings:
        return "warning"
    return "info"


def build_pipeline_summary(pipeline_log: dict) -> str:
    steps = pipeline_log.get("steps", [])
    failed_count = sum(1 for step in steps if step.get("status") == "failed")
    warning_count = len(pipeline_log.get("warnings") or [])
    error_count = len(pipeline_log.get("errors") or [])
    return (
        f"{pipeline_log.get('pipeline', 'daily')} pipeline finished with "
        f"status={pipeline_log.get('status', 'unknown')}. "
        f"failed_steps={failed_count}, warnings={warning_count}, errors={error_count}."
    )


def build_pipeline_alert_text(pipeline_log: dict) -> str:
    lines = [
        f"Pipeline: {pipeline_log.get('pipeline', 'daily')}",
        f"Status: {pipeline_log.get('status', 'unknown')}",
        f"Started: {pipeline_log.get('started_at', '')}",
        f"Finished: {pipeline_log.get('finished_at', '')}",
        "",
        "Summary:",
        build_pipeline_summary(pipeline_log),
        "",
        "Issues:",
    ]
    issues = (pipeline_log.get("errors") or []) + (pipeline_log.get("warnings") or [])
    if issues:
        lines.extend(format_issue_text(issue) for issue in issues)
    else:
        lines.append("- No issue details were attached.")
    lines.extend(
        [
            "",
            f"Log: {pipeline_log.get('log_path', '')}",
            f"Latest log: {pipeline_log.get('latest_log_path', '')}",
        ]
    )
    return "\n".join(lines)


def build_generic_alert_text(alert: dict) -> str:
    lines = [
        f"Pipeline: {alert.get('pipeline', '')}",
        f"Status: {alert.get('status', '')}",
        "",
        "Summary:",
        str(alert.get("summary", "")),
    ]
    if alert.get("run_url"):
        lines.extend(["", f"GitHub run: {alert['run_url']}"])
    if alert.get("log_path"):
        lines.append(f"Log: {alert['log_path']}")
    return "\n".join(lines)


def format_issue_text(issue: dict) -> str:
    step = issue.get("step", "unknown")
    status = issue.get("status", "unknown")
    message = issue.get("message", "")
    return f"- {step} [{status}]: {message}"


def build_pipeline_alert_html(pipeline_log: dict, *, severity: str) -> str:
    badge = status_badge(str(pipeline_log.get("status", "unknown")), severity)
    issue_rows = build_issue_rows(
        (pipeline_log.get("errors") or []) + (pipeline_log.get("warnings") or [])
    )
    step_rows = build_step_rows(pipeline_log.get("steps", []))
    return base_html(
        title="Market Agent Pipeline Alert",
        badge=badge,
        body=f"""
        <p>{escape(build_pipeline_summary(pipeline_log))}</p>
        <table>
          <tr><th>Pipeline</th><td>{escape(pipeline_log.get("pipeline", "daily"))}</td></tr>
          <tr><th>Started</th><td>{escape(pipeline_log.get("started_at", ""))}</td></tr>
          <tr><th>Finished</th><td>{escape(pipeline_log.get("finished_at", ""))}</td></tr>
          <tr><th>Duration</th><td>{escape(str(pipeline_log.get("duration_seconds", "")))} sec</td></tr>
        </table>
        <h2>Issues</h2>
        {issue_rows}
        <h2>Step Status</h2>
        {step_rows}
        <h2>Action Needed</h2>
        <ul>
          <li>Check the failed or warning steps above.</li>
          <li>Open the pipeline log or GitHub artifact for full details.</li>
          <li>Re-run the pipeline if the provider or Supabase error looks temporary.</li>
        </ul>
        <p class="muted">Log: {escape(pipeline_log.get("log_path", ""))}</p>
        <p class="muted">Latest log: {escape(pipeline_log.get("latest_log_path", ""))}</p>
        """,
    )


def build_generic_alert_html(alert: dict) -> str:
    badge = status_badge(str(alert.get("status", "unknown")), alert.get("severity", "warning"))
    run_url_html = (
        f'<p class="muted">GitHub run: <a href="{escape(alert["run_url"])}">'
        f'{escape(alert["run_url"])}</a></p>'
        if alert.get("run_url")
        else ""
    )
    log_html = (
        f'<p class="muted">Log: {escape(alert["log_path"])}</p>'
        if alert.get("log_path")
        else ""
    )
    return base_html(
        title="Market Agent GitHub Action Alert",
        badge=badge,
        body=f"""
        <p>{escape(alert.get("summary", ""))}</p>
        <table>
          <tr><th>Pipeline</th><td>{escape(alert.get("pipeline", ""))}</td></tr>
          <tr><th>Status</th><td>{escape(alert.get("status", ""))}</td></tr>
        </table>
        <h2>Action Needed</h2>
        <ul>
          <li>Open the failed GitHub Actions run.</li>
          <li>Check whether the failure happened before the pipeline could write a log.</li>
          <li>Re-run the workflow after fixing secrets, provider, or dependency issues.</li>
        </ul>
        {run_url_html}
        {log_html}
        """,
    )


def build_issue_rows(issues: list[dict]) -> str:
    if not issues:
        return '<p class="muted">No issue details were attached.</p>'
    rows = []
    for issue in issues:
        rows.append(
            "<tr>"
            f"<td>{escape(issue.get('step', 'unknown'))}</td>"
            f"<td>{status_badge(issue.get('status', 'unknown'), 'warning')}</td>"
            f"<td>{escape(issue.get('message', ''))}</td>"
            "</tr>"
        )
    return "<table><tr><th>Step</th><th>Status</th><th>Message</th></tr>" + "".join(rows) + "</table>"


def build_step_rows(steps: list[dict]) -> str:
    if not steps:
        return '<p class="muted">No step data was attached.</p>'
    rows = []
    for step in steps:
        status = str(step.get("status", "unknown"))
        rows.append(
            "<tr>"
            f"<td>{escape(step.get('name', 'unknown'))}</td>"
            f"<td>{status_badge(status, classify_alert_severity(status=status, warnings=[], errors=[]))}</td>"
            f"<td>{escape(str(step.get('attempts', '')))}</td>"
            f"<td>{escape(str(step.get('duration_seconds', '')))}</td>"
            "</tr>"
        )
    return "<table><tr><th>Step</th><th>Status</th><th>Attempts</th><th>Seconds</th></tr>" + "".join(rows) + "</table>"


def base_html(*, title: str, badge: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; color: #2d2a26; background: #f7f3ec; margin: 0; padding: 24px; }}
    .card {{ max-width: 760px; margin: 0 auto; background: #fffdf8; border: 1px solid #ded6c8; border-radius: 8px; padding: 24px; }}
    h1 {{ font-size: 22px; margin: 0 0 12px; }}
    h2 {{ font-size: 15px; margin: 24px 0 10px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border-bottom: 1px solid #eee7dc; padding: 8px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: #686056; width: 150px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 700; }}
    .critical {{ color: #7f1d1d; background: #fee2e2; border: 1px solid #fecaca; }}
    .warning {{ color: #7c3f00; background: #ffedd5; border: 1px solid #fed7aa; }}
    .info {{ color: #14532d; background: #dcfce7; border: 1px solid #bbf7d0; }}
    .muted {{ color: #776f64; font-size: 12px; }}
    a {{ color: #0f766e; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{escape(title)}</h1>
    <p>{badge}</p>
    {body}
  </div>
</body>
</html>"""


def status_badge(status: str, severity: str) -> str:
    css_class = "critical" if severity == "critical" else "warning" if severity == "warning" else "info"
    return f'<span class="badge {css_class}">{escape(status)}</span>'


def escape(value) -> str:
    return html.escape(str(value or ""))


def send_alert_email(
    alert: dict,
    *,
    config: AlertEmailConfig | None = None,
    smtp_factory: Callable[..., smtplib.SMTP] | None = None,
) -> dict:
    config = config or load_alert_email_config()
    if not config.enabled:
        return {"status": "skipped", "reason": "disabled", "alert": alert}
    validation_error = validate_config(config)
    if validation_error:
        return {"status": "skipped", "reason": validation_error, "alert": alert}

    message = EmailMessage()
    message["Subject"] = alert["subject"]
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message.set_content(alert.get("text", ""))
    message.add_alternative(alert.get("html", ""), subtype="html")

    factory = smtp_factory or smtplib.SMTP
    try:
        with factory(config.smtp_host, config.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(config.sender, config.password)
            smtp.send_message(message)
    except Exception as exc:  # Alert failures should never break the data pipeline.
        return {
            "status": "failed",
            "reason": "send_failed",
            "error": str(exc),
            "subject": alert["subject"],
        }

    return {
        "status": "sent",
        "provider": config.provider,
        "recipients": list(config.recipients),
        "subject": alert["subject"],
    }


def validate_config(config: AlertEmailConfig) -> str | None:
    if config.provider != "gmail":
        return "unsupported_provider"
    if not config.sender:
        return "missing_sender"
    if not config.recipients:
        return "missing_recipients"
    if not config.password:
        return "missing_password"
    return None


def load_pipeline_log(path: str | Path) -> dict:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))
