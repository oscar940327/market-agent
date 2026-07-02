import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts import load_alert_email_config, send_alert_email  # noqa: E402
from ml_monitoring import (  # noqa: E402
    build_model_acceptance_email_summary,
    build_model_acceptance_report,
    build_model_acceptance_summary_markdown,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build ML model upgrade review report.")
    parser.add_argument("--production-metrics-path")
    parser.add_argument("--candidate-metrics-path")
    parser.add_argument("--candidate-calibration-path")
    parser.add_argument("--drift-path")
    parser.add_argument("--production-model-version")
    parser.add_argument("--candidate-model-version")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--send-alert", action="store_true")
    parser.add_argument("--dry-run-alert", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_model_acceptance_report(
        production_metrics=load_optional_json(args.production_metrics_path),
        candidate_metrics=load_optional_json(args.candidate_metrics_path),
        candidate_calibration=load_optional_json(args.candidate_calibration_path),
        drift_report=load_optional_json(args.drift_path),
        production_model_version=args.production_model_version,
        candidate_model_version=args.candidate_model_version,
    )
    output_paths = write_model_upgrade_review_reports(report, output_dir=Path(args.output_dir))
    alert_result = maybe_send_alert(report, output_paths=output_paths, args=args)

    print(f"recommendation={report['recommendation']}")
    print(f"checks={len(report['checks'])}")
    print(f"alert_should_send={report['alert']['should_alert']}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    if alert_result:
        print(f"alert_status={alert_result['status']}")
        if alert_result.get("reason"):
            print(f"alert_reason={alert_result['reason']}")
    for check in report["checks"]:
        if check["status"] in {"reject", "manual_review"}:
            print(
                f"warning=ml_model_upgrade:{check.get('metric') or check['name']}:"
                f"{check['message']}"
            )
    return 0


def load_optional_json(path: str | None) -> dict | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_model_upgrade_review_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = build_report_suffix(report)
    json_path = output_dir / f"ml_model_upgrade_review_{suffix}.json"
    markdown_path = output_dir / f"ml_model_upgrade_review_{suffix}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_model_acceptance_summary_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def build_report_suffix(report: dict) -> str:
    production = report.get("production_model_version") or "production"
    candidate = report.get("candidate_model_version") or "candidate"
    return f"{sanitize(production)}_vs_{sanitize(candidate)}_v1"


def sanitize(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def maybe_send_alert(report: dict, *, output_paths: dict[str, str], args: argparse.Namespace) -> dict | None:
    if not args.send_alert:
        return None
    if not report["alert"]["should_alert"]:
        return {"status": "skipped", "reason": "no_action_needed"}

    alert = build_model_upgrade_alert(report, output_paths=output_paths)
    if args.dry_run_alert:
        return {"status": "dry_run", "reason": "not_sent", "alert": alert}
    return send_alert_email(alert, config=load_alert_email_config())


def build_model_upgrade_alert(report: dict, *, output_paths: dict[str, str]) -> dict:
    recommendation = report["recommendation"]
    severity = report["alert"]["severity"]
    summary = build_model_acceptance_email_summary(report)
    subject = f"[Market Agent] ML model upgrade review: {recommendation}"
    text = "\n".join(
        [
            "Pipeline: ml-model-upgrade-review",
            f"Recommendation: {recommendation}",
            "",
            summary,
            "",
            f"Report: {output_paths['json_path']}",
            f"Summary: {output_paths['markdown_path']}",
        ]
    )
    html = build_model_upgrade_alert_html(
        report,
        output_paths=output_paths,
        summary=summary,
        severity=severity,
    )
    return {
        "should_send": True,
        "reason": report["alert"]["reason"],
        "subject": subject,
        "severity": severity,
        "pipeline": "ml-model-upgrade-review",
        "status": recommendation,
        "summary": summary,
        "warnings": [
            {
                "step": "model_upgrade_review",
                "status": check["status"],
                "message": check["message"],
            }
            for check in report["checks"]
            if check["status"] in {"reject", "manual_review"}
        ],
        "errors": [],
        "failed_steps": [],
        "log_path": output_paths["json_path"],
        "latest_log_path": output_paths["markdown_path"],
        "text": text,
        "html": html,
    }


def build_model_upgrade_alert_html(
    report: dict,
    *,
    output_paths: dict[str, str],
    summary: str,
    severity: str,
) -> str:
    badge_class = "warning" if severity == "warning" else "info"
    rows = "".join(
        "<tr>"
        f"<td>{escape(check['name'])}</td>"
        f"<td>{escape(check['status'])}</td>"
        f"<td>{escape(check['message'])}</td>"
        "</tr>"
        for check in report["checks"]
        if check["status"] in {"reject", "manual_review"}
    )
    if not rows:
        rows = '<tr><td colspan="3">No blocking checks.</td></tr>'
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
    .warning {{ color: #7c3f00; background: #ffedd5; border: 1px solid #fed7aa; }}
    .info {{ color: #14532d; background: #dcfce7; border: 1px solid #bbf7d0; }}
    .muted {{ color: #776f64; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Market Agent ML Model Upgrade Review</h1>
    <p><span class="badge {badge_class}">{escape(report["recommendation"])}</span></p>
    <p>{escape(summary).replace(chr(10), "<br>")}</p>
    <table>
      <tr><th>Production model</th><td>{escape(report.get("production_model_version") or "unknown")}</td></tr>
      <tr><th>Candidate model</th><td>{escape(report.get("candidate_model_version") or "unknown")}</td></tr>
    </table>
    <h2>Checks Needing Attention</h2>
    <table><tr><th>Check</th><th>Status</th><th>Message</th></tr>{rows}</table>
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
