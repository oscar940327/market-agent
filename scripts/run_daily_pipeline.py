import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts import send_pipeline_alert_if_needed  # noqa: E402


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: list[str]
    core: bool
    retryable: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local daily Market Agent data pipeline.",
    )
    parser.add_argument(
        "--only",
        choices=["all", "prices", "news", "freshness"],
        default="all",
        help="Run one pipeline slice. Default: all.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers for test runs.")
    parser.add_argument("--limit", type=int, help="Limit universe tickers for test runs.")
    parser.add_argument("--news-max-items", type=int, default=5)
    parser.add_argument("--news-limit", type=int, default=50)
    parser.add_argument(
        "--skip-news",
        action="store_true",
        help="Skip news ingestion/classification/summary in the full pipeline.",
    )
    parser.add_argument(
        "--skip-llm-news",
        action="store_true",
        help="Use rule_based news classification instead of LLM classification.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Do not send email alerts even when ALERT_EMAIL_ENABLED=true.",
    )
    parser.add_argument(
        "--log-dir",
        default=str(PROJECT_ROOT / "data" / "pipeline_runs"),
    )
    return parser


def build_pipeline_steps(args: argparse.Namespace) -> list[PipelineStep]:
    steps: list[PipelineStep] = []

    if args.only in {"all", "prices"}:
        steps.extend(build_price_steps(args))

    if args.only == "freshness":
        steps.append(
            PipelineStep(
                name="freshness_check",
                command=script_command("check_freshness.py"),
                core=True,
                retryable=False,
            )
        )

    if args.only in {"all", "news"} and not args.skip_news:
        steps.extend(build_news_steps(args))

    if args.only == "all":
        steps.append(
            PipelineStep(
                name="research_outcomes",
                command=script_command("compute_research_outcomes.py", "--limit", "100"),
                core=False,
                retryable=True,
            )
        )
        steps.append(
            PipelineStep(
                name="ml_prediction_outcomes",
                command=script_command(
                    "compute_ml_prediction_outcomes.py",
                    "--limit",
                    "100",
                ),
                core=False,
                retryable=True,
            )
        )

    return steps


def build_price_steps(args: argparse.Namespace) -> list[PipelineStep]:
    tickers_args = optional_tickers_and_limit(args)
    return [
        PipelineStep(
            name="benchmark_prices",
            command=script_command("ingest_benchmark.py"),
            core=True,
            retryable=True,
        ),
        PipelineStep(
            name="daily_prices",
            command=script_command("ingest_daily_prices.py", *tickers_args),
            core=True,
            retryable=True,
        ),
        PipelineStep(
            name="benchmark_technical_features",
            command=script_command("compute_technical_features.py", "--tickers", "QQQ"),
            core=True,
            retryable=True,
        ),
        PipelineStep(
            name="technical_features",
            command=script_command("compute_technical_features.py", *tickers_args),
            core=True,
            retryable=True,
        ),
        PipelineStep(
            name="market_regimes",
            command=script_command("compute_market_regime.py"),
            core=True,
            retryable=True,
        ),
        PipelineStep(
            name="freshness_check",
            command=script_command("check_freshness.py", "--scope", "prices"),
            core=True,
            retryable=False,
        ),
    ]


def build_news_steps(args: argparse.Namespace) -> list[PipelineStep]:
    ticker_args = optional_tickers_and_limit(args)
    classifier_mode = "rule_based" if args.skip_llm_news else "llm"
    classifier_args = optional_tickers(args) + ["--mode", classifier_mode, "--limit", str(args.news_limit)]
    summary_args = optional_tickers(args) + ["--limit", str(args.news_limit)]

    return [
        PipelineStep(
            name="news_ingestion",
            command=script_command(
                "ingest_news_events.py",
                "--max-items",
                str(args.news_max_items),
                *ticker_args,
            ),
            core=False,
            retryable=True,
        ),
        PipelineStep(
            name="news_classification",
            command=script_command("classify_news_events.py", *classifier_args),
            core=False,
            retryable=True,
        ),
        PipelineStep(
            name="news_summary",
            command=script_command("summarize_news_events.py", *summary_args),
            core=False,
            retryable=True,
        ),
    ]


def optional_tickers_and_limit(args: argparse.Namespace) -> list[str]:
    values = optional_tickers(args)
    if args.limit is not None:
        values.extend(["--limit", str(args.limit)])
    return values


def optional_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return ["--tickers", args.tickers]
    return []


def script_command(script_name: str, *args: str) -> list[str]:
    return [sys.executable, str(PROJECT_ROOT / "scripts" / script_name), *args]


def run_pipeline(
    args: argparse.Namespace,
    *,
    command_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> dict:
    started_at = datetime.now(UTC)
    steps = build_pipeline_steps(args)
    results = []

    for step in steps:
        results.append(run_step(step, args.dry_run, command_runner=command_runner))

    status = determine_pipeline_status(results)
    finished_at = datetime.now(UTC)
    warnings = build_pipeline_issues(results, issue_type="warning")
    errors = build_pipeline_issues(results, issue_type="error")
    log_paths = build_pipeline_log_paths(args.log_dir)
    log = {
        "pipeline": "daily",
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "log_path": str(log_paths["timestamped"]),
        "latest_log_path": str(log_paths["latest"]),
        "options": {
            "only": args.only,
            "tickers": args.tickers,
            "limit": args.limit,
            "skip_news": args.skip_news,
            "skip_llm_news": args.skip_llm_news,
            "dry_run": args.dry_run,
            "no_alert": args.no_alert,
        },
        "warnings": warnings,
        "errors": errors,
        "steps": results,
    }
    write_pipeline_log(log, log_paths)
    if not args.no_alert:
        alert_result = send_pipeline_alert_if_needed(log)
        log["alert"] = summarize_alert_result(alert_result)
        write_pipeline_log(log, log_paths)
    return log


def run_step(
    step: PipelineStep,
    dry_run: bool,
    *,
    command_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> dict:
    started_at = datetime.now(UTC)
    max_attempts = 2 if step.retryable else 1
    attempts = 0
    last_result = None

    if dry_run:
        return {
            "name": step.name,
            "status": "dry_run",
            "core": step.core,
            "retryable": step.retryable,
            "attempts": 0,
            "command": sanitize_command(step.command),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 0,
            "returncode": None,
            "metrics": {},
            "stdout_tail": "",
            "stderr_tail": "",
        }

    runner = command_runner or default_command_runner
    while attempts < max_attempts:
        attempts += 1
        last_result = runner(step.command)
        if last_result.returncode == 0:
            break
        if attempts < max_attempts:
            time.sleep(1)

    finished_at = datetime.now(UTC)
    stdout = last_result.stdout if last_result else ""
    stderr = last_result.stderr if last_result else ""
    return {
        "name": step.name,
        "status": "success" if last_result and last_result.returncode == 0 else "failed",
        "core": step.core,
        "retryable": step.retryable,
        "attempts": attempts,
        "command": sanitize_command(step.command),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "returncode": last_result.returncode if last_result else None,
        "metrics": parse_step_metrics(stdout),
        "stdout_tail": tail_text(stdout),
        "stderr_tail": tail_text(stderr),
    }


def default_command_runner(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def determine_pipeline_status(results: list[dict]) -> str:
    failed = [result for result in results if result["status"] == "failed"]
    if any(result["core"] for result in failed):
        return "failed"
    if failed:
        return "partial_success"
    return "success"


def build_pipeline_issues(results: list[dict], *, issue_type: str) -> list[dict]:
    issues = []
    for result in results:
        if issue_type == "error" and result["status"] == "failed" and result["core"]:
            issues.append(build_step_issue(result))
        elif issue_type == "warning":
            if result["status"] == "failed" and not result["core"]:
                issues.append(build_step_issue(result))
            for key, value in result.get("metrics", {}).items():
                if str(key).startswith("warning"):
                    issues.append(
                        {
                            "step": result["name"],
                            "status": result["status"],
                            "message": str(value),
                        }
                    )
    return issues


def build_step_issue(result: dict) -> dict:
    message = (
        result.get("stderr_tail")
        or result.get("stdout_tail")
        or f"Step {result['name']} failed."
    )
    return {
        "step": result["name"],
        "status": result["status"],
        "returncode": result.get("returncode"),
        "message": tail_text(message, max_chars=1000),
    }


def build_pipeline_log_paths(log_dir: str | Path) -> dict[str, Path]:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    return {
        "timestamped": directory / f"daily_pipeline_{timestamp}.json",
        "latest": directory / "latest_daily_pipeline.json",
    }


def write_pipeline_log(log: dict, paths: dict[str, Path]) -> None:
    paths["timestamped"].write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["latest"].write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def summarize_alert_result(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "error": result.get("error"),
        "subject": result.get("subject"),
        "recipients": result.get("recipients", []),
    }


def sanitize_command(command: list[str]) -> list[str]:
    return [str(part) for part in command]


def tail_text(value: str, *, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def parse_step_metrics(stdout: str) -> dict:
    metrics = {}
    repeated_keys = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or any(character.isspace() for character in key):
            continue
        parsed_value = parse_metric_value(value)
        if key in metrics:
            repeated_keys.setdefault(key, [metrics[key]]).append(parsed_value)
            metrics[key] = repeated_keys[key]
        else:
            metrics[key] = parsed_value
    return metrics


def parse_metric_value(value: str):
    if value == "":
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "none" or lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def main() -> int:
    args = build_parser().parse_args()
    log = run_pipeline(args)
    print(f"pipeline_status={log['status']}")
    print(f"log_path={log['log_path']}")
    for step in log["steps"]:
        print(
            f"step={step['name']} status={step['status']} "
            f"attempts={step['attempts']}"
        )

    return 1 if log["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
