import subprocess

from alerts.email_alerts import (
    AlertEmailConfig,
    build_github_action_alert,
    build_pipeline_alert,
    send_alert_email,
)
from scripts.run_daily_pipeline import build_parser, run_pipeline


def parse_args(values):
    return build_parser().parse_args(values)


def make_pipeline_log(status="partial_success"):
    return {
        "pipeline": "daily",
        "status": status,
        "started_at": "2026-07-02T01:00:00+00:00",
        "finished_at": "2026-07-02T01:02:00+00:00",
        "duration_seconds": 120,
        "log_path": "data/pipeline_runs/daily_pipeline.json",
        "latest_log_path": "data/pipeline_runs/latest_daily_pipeline.json",
        "warnings": [
            {
                "step": "news_ingestion",
                "status": "failed",
                "message": "news provider unavailable",
            }
        ],
        "errors": [],
        "steps": [
            {
                "name": "daily_prices",
                "status": "success",
                "attempts": 1,
                "duration_seconds": 1.0,
            },
            {
                "name": "news_ingestion",
                "status": "failed",
                "attempts": 2,
                "duration_seconds": 2.0,
            },
        ],
    }


def test_build_pipeline_alert_sends_for_partial_success():
    alert = build_pipeline_alert(make_pipeline_log())

    assert alert["should_send"] is True
    assert alert["severity"] == "warning"
    assert "partial_success" in alert["subject"]
    assert "news provider unavailable" in alert["text"]
    assert "Market Agent Pipeline Alert" in alert["html"]


def test_build_pipeline_alert_skips_clean_success():
    log = make_pipeline_log(status="success")
    log["warnings"] = []
    log["steps"][1]["status"] = "success"

    alert = build_pipeline_alert(log)

    assert alert["should_send"] is False
    assert alert["reason"] == "pipeline_success"


def test_send_alert_email_skips_when_disabled():
    config = AlertEmailConfig(
        enabled=False,
        provider="gmail",
        sender="sender@example.com",
        recipients=("receiver@example.com",),
        password="password",
    )

    result = send_alert_email(build_pipeline_alert(make_pipeline_log()), config=config)

    assert result["status"] == "skipped"
    assert result["reason"] == "disabled"


def test_send_alert_email_uses_smtp_when_enabled():
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def starttls(self):
            return None

        def login(self, sender, password):
            self.sender = sender
            self.password = password

        def send_message(self, message):
            sent_messages.append(message)

    config = AlertEmailConfig(
        enabled=True,
        provider="gmail",
        sender="sender@example.com",
        recipients=("receiver@example.com",),
        password="password",
    )

    result = send_alert_email(
        build_pipeline_alert(make_pipeline_log()),
        config=config,
        smtp_factory=FakeSMTP,
    )

    assert result["status"] == "sent"
    assert result["recipients"] == ["receiver@example.com"]
    assert sent_messages[0]["To"] == "receiver@example.com"


def test_github_action_alert_has_run_url():
    alert = build_github_action_alert(
        pipeline="daily-prices",
        status="failed",
        message="workflow failed",
        run_url="https://github.com/example/repo/actions/runs/1",
    )

    assert alert["should_send"] is True
    assert alert["severity"] == "critical"
    assert "workflow failed" in alert["text"]
    assert "actions/runs/1" in alert["html"]


def test_run_pipeline_records_skipped_alert_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_ENABLED", "false")
    args = parse_args(["--only", "news", "--tickers", "MU", "--log-dir", str(tmp_path)])

    def fake_runner(command):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="warning=news temporarily unavailable",
            stderr="news unavailable",
        )

    log = run_pipeline(args, command_runner=fake_runner)

    assert log["status"] == "partial_success"
    assert log["alert"]["status"] == "skipped"
    assert log["alert"]["reason"] == "disabled"
