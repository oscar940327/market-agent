import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts import load_alert_email_config, send_alert_email  # noqa: E402
from ml_monitoring import (  # noqa: E402
    build_ml_health_email_summary,
    build_ml_health_report,
    build_ml_health_summary_markdown,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build combined ML health report.")
    parser.add_argument("--metrics-path")
    parser.add_argument("--calibration-path")
    parser.add_argument("--drift-path")
    parser.add_argument(
        "--drift-policy",
        choices=["required", "scheduled_weekly"],
        default="required",
        help="Use scheduled_weekly for daily reports where full drift runs in the weekly dataset workflow.",
    )
    parser.add_argument("--model-upgrade-path")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--send-alert", action="store_true")
    parser.add_argument("--dry-run-alert", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    report = build_ml_health_report(
        metrics_report=load_report(args.metrics_path, output_dir, "ml_metrics_report_*.json"),
        calibration_report=load_report(args.calibration_path, output_dir, "ml_calibration_report_*.json"),
        drift_report=load_report(args.drift_path, output_dir, "ml_drift_report_*.json"),
        model_upgrade_report=load_report(args.model_upgrade_path, output_dir, "ml_model_upgrade_review_*.json"),
        drift_policy=args.drift_policy,
    )
    output_paths = write_ml_health_reports(report, output_dir=output_dir)
    alert_result = maybe_send_alert(report, output_paths=output_paths, args=args)

    print(f"overall_status={report['overall_status']}")
    print(f"ml_reference_policy={report['ml_reference_policy']['status']}")
    print(f"warnings={len(report['warnings'])}")
    print(f"alert_should_send={report['alert']['should_alert']}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    if alert_result:
        print(f"alert_status={alert_result['status']}")
        if alert_result.get("reason"):
            print(f"alert_reason={alert_result['reason']}")
    for warning in report["warnings"]:
        print(
            f"warning=ml_health:{warning.get('source', 'unknown')}:"
            f"{warning.get('message', '')}"
        )
    return 0


def load_report(path: str | None, output_dir: Path, pattern: str) -> dict | None:
    if path:
        return load_json(Path(path))
    latest = find_latest_report(output_dir, pattern)
    return load_json(latest) if latest else None


def find_latest_report(output_dir: Path, pattern: str) -> Path | None:
    if not output_dir.exists():
        return None
    paths = list(output_dir.glob(pattern))
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_ml_health_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ml_health_report_v1.json"
    markdown_path = output_dir / "ml_health_summary_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_ml_health_summary_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def maybe_send_alert(report: dict, *, output_paths: dict[str, str], args: argparse.Namespace) -> dict | None:
    if not args.send_alert:
        return None
    if not report["alert"]["should_alert"]:
        return {"status": "skipped", "reason": "healthy"}

    alert = build_ml_health_alert(report, output_paths=output_paths)
    if args.dry_run_alert:
        return {"status": "dry_run", "reason": "not_sent", "alert": alert}
    return send_alert_email(alert, config=load_alert_email_config())


def build_ml_health_alert(report: dict, *, output_paths: dict[str, str]) -> dict:
    summary = build_ml_health_email_summary(report)
    severity = report["alert"]["severity"]
    subject = f"[Market Agent] ML health: {report['overall_status']}"
    text = "\n".join(
        [
            "Pipeline: ml-health-report",
            f"Status: {report['overall_status']}",
            "",
            summary,
            "",
            f"Report: {output_paths['json_path']}",
            f"Summary: {output_paths['markdown_path']}",
        ]
    )
    return {
        "should_send": True,
        "reason": report["alert"]["reason"],
        "subject": subject,
        "severity": severity,
        "pipeline": "ml-health-report",
        "status": report["overall_status"],
        "summary": summary,
        "warnings": [
            {
                "step": warning.get("source", "ml_health"),
                "status": warning.get("status", report["overall_status"]),
                "message": warning.get("message", ""),
            }
            for warning in report["warnings"]
        ],
        "errors": [],
        "failed_steps": [],
        "log_path": output_paths["json_path"],
        "latest_log_path": output_paths["markdown_path"],
        "text": text,
        "html": build_ml_health_alert_html(report, output_paths=output_paths, summary=summary),
    }


def build_ml_health_alert_html(report: dict, *, output_paths: dict[str, str], summary: str) -> str:
    severity = report["alert"]["severity"]
    badge_class = "critical" if severity == "critical" else "warning" if severity == "warning" else "info"
    component_rows = "".join(
        "<tr>"
        f"<td>{escape(component['name'])}</td>"
        f"<td>{escape(component['status'])}</td>"
        f"<td>{escape(component['summary'])}</td>"
        f"<td>{escape(component['action'])}</td>"
        "</tr>"
        for component in report["components"].values()
    )
    action_items = "".join(f"<li>{escape(action)}</li>" for action in report["action_needed"])
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
    .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 700; }}
    .critical {{ color: #7f1d1d; background: #fee2e2; border: 1px solid #fecaca; }}
    .warning {{ color: #7c3f00; background: #ffedd5; border: 1px solid #fed7aa; }}
    .info {{ color: #14532d; background: #dcfce7; border: 1px solid #bbf7d0; }}
    .muted {{ color: #776f64; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Market Agent ML Health Report</h1>
    <p><span class="badge {badge_class}">{escape(report["overall_status"])}</span></p>
    <p>{escape(summary).replace(chr(10), "<br>")}</p>
    <h2>Components</h2>
    <table><tr><th>Component</th><th>Status</th><th>Summary</th><th>Action</th></tr>{component_rows}</table>
    <h2>Action Needed</h2>
    <ul>{action_items}</ul>
    <p class="muted">Report: {escape(output_paths["json_path"])}</p>
    <p class="muted">Summary: {escape(output_paths["markdown_path"])}</p>
  </div>
</body>
</html>"""


def escape(value) -> str:
    import html

    return html.escape(str(value or ""))


if __name__ == "__main__":
    raise SystemExit(main())
