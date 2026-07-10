import argparse
import html
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent.reporting import build_report  # noqa: E402
from agent.rule_based_router import detect_intent  # noqa: E402
from alerts import load_alert_email_config, send_alert_email  # noqa: E402
from data_store.supabase_store import insert_research_log, upsert_research_outcomes  # noqa: E402
from log_research_result import run_research_workflow  # noqa: E402
from research_logging import (  # noqa: E402
    build_research_log_row,
    build_research_outcome_rows_for_data,
)


DEFAULT_RESEARCH_FIXTURES = (
    "MU 現在適合進場嗎",
    "記憶體類股現在適合進場觀察嗎",
    "MU 突破策略以前表現怎麼樣",
    "MU 如果我已經持有，現在要不要減碼",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log daily research fixture questions for Step 21 outcome tracking.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Research question to log. Can be passed multiple times.",
    )
    parser.add_argument("--analyst-mode", default="rule_based")
    parser.add_argument("--include-news", action="store_true", default=True)
    parser.add_argument("--exclude-news", action="store_false", dest="include_news")
    parser.add_argument("--include-fundamentals", action="store_true", default=True)
    parser.add_argument(
        "--exclude-fundamentals",
        action="store_false",
        dest="include_fundamentals",
    )
    parser.add_argument("--skip-outcomes", action="store_true")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run-email", action="store_true")
    parser.add_argument(
        "--report-frequency",
        choices=("daily", "weekly"),
        default="daily",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "data" / "research_reports"),
    )
    args = parser.parse_args()

    queries = args.query or list(DEFAULT_RESEARCH_FIXTURES)
    failures = 0
    fixture_results = []

    for query in queries:
        result = log_one_fixture(query=query, args=args)
        fixture_results.append(result)
        print(
            "query="
            f"{query} status={result['status']} intent={result.get('intent')} "
            f"tracking_status={result.get('tracking_status')} "
            f"outcomes={result.get('outcome_count', 0)}"
        )
        if result["status"] != "success":
            failures += 1
            print(f"message={result.get('message')}")

    report = build_daily_research_fixture_report(
        fixture_results,
        frequency=args.report_frequency,
    )
    output_paths = write_daily_research_fixture_report(
        report,
        output_dir=Path(args.output_dir),
    )
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")

    if args.send_email:
        email_result = send_daily_research_fixture_email(
            report,
            output_paths=output_paths,
            dry_run=args.dry_run_email,
        )
        print(f"email={email_result['status']}")
        if email_result.get("reason"):
            print(f"email_reason={email_result['reason']}")

    print(f"fixtures={len(queries)}")
    print(f"failures={failures}")
    return 1 if failures else 0


def log_one_fixture(*, query: str, args: argparse.Namespace) -> dict:
    route = detect_intent(query)
    intent = route["intent"]
    workflow_args = SimpleNamespace(
        ticker=None,
        query=query,
        analyst_mode=args.analyst_mode,
        include_news=args.include_news,
        include_fundamentals=args.include_fundamentals,
    )
    data, report_kind = run_research_workflow(args=workflow_args, intent=intent)
    if data.get("status") != "success":
        return {
            "status": "error",
            "intent": intent,
            "query": query,
            "message": data.get("message") or data.get("status"),
        }

    report_result = build_report(
        kind=report_kind,
        data=data,
        analyst_mode=args.analyst_mode,
    )
    request_options = {
        "include_news": args.include_news,
        "include_fundamentals": args.include_fundamentals,
        "include_technicals": True,
        "analyst_mode": args.analyst_mode,
        "fixture": True,
    }
    log_row = build_research_log_row(
        query=query,
        intent=intent,
        data=data,
        report=report_result["report"],
        request_options=request_options,
        output_snapshot={
            "data": data,
            "analyst": report_result["analyst"],
            "fixture": True,
        },
    )
    log_result = insert_research_log(log_row)
    if log_result["status"] != "success":
        return {
            "status": "error",
            "intent": intent,
            "query": query,
            "report": report_result["report"],
            "tracking_status": log_row.get("tracking_status"),
            "message": log_result.get("message"),
        }

    outcome_rows = []
    if not args.skip_outcomes:
        outcome_rows = build_research_outcome_rows_for_data(
            research_log_id=log_result["row"]["id"],
            data=data,
            query_date=date.today(),
            intent=intent,
        )
    outcome_result = upsert_research_outcomes(outcome_rows)
    if outcome_result["status"] not in {"success", "skipped"}:
        return {
            "status": "error",
            "intent": intent,
            "query": query,
            "report": report_result["report"],
            "tracking_status": log_row.get("tracking_status"),
            "message": outcome_result.get("message"),
        }

    return {
        "status": "success",
        "intent": intent,
        "query": query,
        "report": report_result["report"],
        "tracking_status": log_row.get("tracking_status"),
        "outcome_count": len(outcome_rows),
        "research_log_id": log_result["row"]["id"],
    }


def build_daily_research_fixture_report(
    results: list[dict],
    *,
    frequency: str = "daily",
) -> dict:
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    status_counts = {}
    for result in results:
        status = result.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "report_version": f"{frequency}_research_fixture_report_v1",
        "frequency": frequency,
        "generated_at": generated_at,
        "fixture_count": len(results),
        "status": "success" if status_counts.get("error", 0) == 0 else "partial_success",
        "status_counts": status_counts,
        "results": results,
    }


def write_daily_research_fixture_report(
    report: dict,
    *,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frequency = report.get("frequency", "daily")
    json_path = output_dir / f"{frequency}_research_fixture_report_v1.json"
    markdown_path = output_dir / f"{frequency}_research_fixture_report_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_daily_research_fixture_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_daily_research_fixture_markdown(report: dict) -> str:
    frequency = report.get("frequency", "daily")
    frequency_title = "Weekly" if frequency == "weekly" else "Daily"
    lines = [
        f"# Market Agent {frequency_title} Research Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Fixtures: `{report['fixture_count']}`",
        "",
    ]

    for index, result in enumerate(report["results"]):
        if index:
            lines.extend(["", "---", ""])
        lines.append(result.get("query") or "Unknown query")
        lines.append("")
        if result.get("status") != "success":
            lines.append("分析或紀錄失敗")
            lines.append("")
            lines.append(f"原因：{result.get('message', 'unknown')}")
            continue
        lines.append(result.get("report", "").strip())

    return "\n".join(lines).rstrip() + "\n"


def send_daily_research_fixture_email(
    report: dict,
    *,
    output_paths: dict[str, str],
    dry_run: bool = False,
) -> dict:
    alert = build_daily_research_fixture_alert(report, output_paths=output_paths)
    if dry_run:
        return {"status": "dry_run", "reason": "not_sent", "alert": alert}
    return send_alert_email(alert, config=load_alert_email_config())


def build_daily_research_fixture_alert(report: dict, *, output_paths: dict[str, str]) -> dict:
    frequency = report.get("frequency", "daily")
    frequency_title = "Weekly" if frequency == "weekly" else "Daily"
    pipeline = f"{frequency}-research-fixtures"
    subject = f"[Market Agent] {frequency_title} research report: {report['status']}"
    markdown = build_daily_research_fixture_markdown(report)
    html_body = html.escape(markdown).replace("\n", "<br>")
    return {
        "subject": subject,
        "severity": "info" if report["status"] == "success" else "warning",
        "pipeline": pipeline,
        "status": report["status"],
        "summary": f"{frequency_title} research fixture report generated with status={report['status']}.",
        "warnings": [],
        "errors": [],
        "failed_steps": [],
        "log_path": output_paths["json_path"],
        "latest_log_path": output_paths["markdown_path"],
        "text": markdown,
        "html": (
            "<html><body style=\"font-family:Arial,sans-serif;line-height:1.45;\">"
            f"<h2>Market Agent {frequency_title} Research Report</h2><p>{html_body}</p>"
            "</body></html>"
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
