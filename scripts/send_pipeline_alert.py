import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts import (  # noqa: E402
    build_github_action_alert,
    load_alert_email_config,
    send_alert_email,
    send_pipeline_alert_if_needed,
)
from alerts.email_alerts import load_pipeline_log  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send Market Agent pipeline email alerts.")
    parser.add_argument("--log-path", help="Pipeline JSON log path.")
    parser.add_argument("--pipeline", default="daily", help="Pipeline or workflow name.")
    parser.add_argument("--status", default="failed", help="Alert status for generic alerts.")
    parser.add_argument("--message", help="Generic alert message.")
    parser.add_argument("--run-url", help="GitHub Actions run URL.")
    parser.add_argument(
        "--skip-if-log-exists",
        help="Skip generic alert when a pipeline log exists, to avoid duplicate emails.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build alert but do not send.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.skip_if_log_exists and Path(args.skip_if_log_exists).exists():
        print("alert_status=skipped")
        print("alert_reason=pipeline_log_exists")
        return 0

    if args.log_path:
        log = load_pipeline_log(args.log_path)
        if args.dry_run:
            result = {"status": "dry_run", "reason": "not_sent"}
        else:
            result = send_pipeline_alert_if_needed(log)
    else:
        alert = build_github_action_alert(
            pipeline=args.pipeline,
            status=args.status,
            message=args.message or "GitHub Actions workflow failed before a pipeline log was available.",
            log_path=args.log_path,
            run_url=args.run_url or build_github_run_url(),
        )
        if args.dry_run:
            result = {"status": "dry_run", "reason": "not_sent", "alert": alert}
        else:
            result = send_alert_email(alert, config=load_alert_email_config())

    print(f"alert_status={result['status']}")
    if result.get("reason"):
        print(f"alert_reason={result['reason']}")
    if result.get("subject"):
        print(f"alert_subject={result['subject']}")
    return 0


def build_github_run_url() -> str | None:
    server_url = os.getenv("GITHUB_SERVER_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if not (server_url and repository and run_id):
        return None
    return f"{server_url}/{repository}/actions/runs/{run_id}"


if __name__ == "__main__":
    raise SystemExit(main())
