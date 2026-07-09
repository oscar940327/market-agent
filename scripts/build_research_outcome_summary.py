import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store import fetch_research_outcomes_for_summary  # noqa: E402
from research_logging import classify_research_outcome_quality  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Step 21 research outcome summary with quality labels.",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--status",
        default="computed",
        help="Outcome status to summarize. Use empty string for all statuses.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "data" / "research_reports"),
    )
    args = parser.parse_args()

    outcomes = fetch_research_outcomes_for_summary(
        limit=args.limit,
        status=args.status or None,
    )
    report = build_research_outcome_summary_report(outcomes)
    output_paths = write_research_outcome_summary_report(
        report,
        output_dir=Path(args.output_dir),
    )

    print(f"outcomes={len(outcomes)}")
    print(f"computed={report['status_counts'].get('computed', 0)}")
    print(f"quality_counts={report['quality_counts']}")
    print(f"json_path={output_paths['json_path']}")
    print(f"markdown_path={output_paths['markdown_path']}")
    return 0


def build_research_outcome_summary_report(outcomes: list[dict]) -> dict:
    enriched = []
    status_counts = defaultdict(int)
    quality_counts = defaultdict(int)
    conclusion_summary = defaultdict(lambda: {"count": 0, "average_return": 0.0})
    exit_signal_summary = defaultdict(lambda: {"count": 0, "average_return": 0.0})

    for outcome in outcomes:
        quality = classify_research_outcome_quality(outcome)
        row = {**outcome, **quality}
        enriched.append(row)
        status_counts[row.get("outcome_status", "unknown")] += 1
        quality_counts[quality["quality"]] += 1
        accumulate_return(conclusion_summary, row.get("conclusion") or "unknown", row)
        accumulate_return(exit_signal_summary, row.get("exit_signal") or "none", row)

    finalize_average_returns(conclusion_summary)
    finalize_average_returns(exit_signal_summary)

    return {
        "report_version": "research_outcome_summary_v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "outcome_count": len(enriched),
        "status_counts": dict(sorted(status_counts.items())),
        "quality_counts": dict(sorted(quality_counts.items())),
        "conclusion_summary": dict(sorted(conclusion_summary.items())),
        "exit_signal_summary": dict(sorted(exit_signal_summary.items())),
        "recent_outcomes": enriched[:20],
    }


def accumulate_return(bucket: dict, key: str, row: dict) -> None:
    return_pct = safe_float(row.get("return_pct"))
    bucket[key]["count"] += 1
    if return_pct is not None:
        bucket[key]["average_return"] += return_pct


def finalize_average_returns(bucket: dict) -> None:
    for value in bucket.values():
        count = value["count"]
        value["average_return"] = round(value["average_return"] / count, 6) if count else None


def write_research_outcome_summary_report(
    report: dict,
    *,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "research_outcome_summary_v1.json"
    markdown_path = output_dir / "research_outcome_summary_v1.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_research_outcome_summary_markdown(report),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_research_outcome_summary_markdown(report: dict) -> str:
    lines = [
        "# Research Outcome Summary",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Outcomes: `{report['outcome_count']}`",
        "",
        "## Quality Counts",
        "",
    ]
    if report["quality_counts"]:
        lines.extend(
            f"- `{quality}`: `{count}`"
            for quality, count in report["quality_counts"].items()
        )
    else:
        lines.append("- No outcomes found.")

    lines.extend(["", "## Conclusion Summary", ""])
    lines.extend(build_group_summary_lines(report["conclusion_summary"]))

    lines.extend(["", "## Exit Signal Summary", ""])
    lines.extend(build_group_summary_lines(report["exit_signal_summary"]))

    lines.extend(["", "## Recent Outcomes", ""])
    if not report["recent_outcomes"]:
        lines.append("- No recent outcomes.")
    for outcome in report["recent_outcomes"][:10]:
        lines.append(
            "- "
            f"{outcome.get('ticker')} {outcome.get('horizon_trading_days')}d "
            f"conclusion={outcome.get('conclusion')} "
            f"return={format_percent(outcome.get('return_pct'))} "
            f"max_drawdown={format_percent(outcome.get('max_drawdown_pct'))} "
            f"quality={outcome.get('quality')} "
            f"reason={outcome.get('quality_reason')}"
        )

    return "\n".join(lines) + "\n"


def build_group_summary_lines(summary: dict) -> list[str]:
    if not summary:
        return ["- No data."]
    return [
        f"- `{key}`: count={value['count']}, average_return={format_percent(value['average_return'])}"
        for key, value in summary.items()
    ]


def format_percent(value) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number * 100:+.1f}%"


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
