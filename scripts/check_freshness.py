import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_freshness import build_current_data_freshness  # noqa: E402
from data_recovery import build_data_recovery_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Market Agent data freshness.")
    parser.add_argument("--ticker", default="QQQ")
    parser.add_argument("--benchmark", default="QQQ")
    parser.add_argument(
        "--scope",
        choices=["all", "prices", "ml_training"],
        default="all",
        help="Use prices to evaluate only market data freshness.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--output",
        default=str(
            PROJECT_ROOT
            / "data"
            / "maintenance"
            / "data_recovery"
            / "latest_data_recovery.json"
        ),
    )
    args = parser.parse_args()

    report = build_current_data_freshness(
        ticker=args.ticker,
        benchmark=args.benchmark,
    )
    report = apply_scope(report, args.scope)
    recovery = build_data_recovery_report(
        freshness=report,
        ticker=args.ticker,
        include_news=args.scope == "all",
        include_fundamentals=args.scope == "all",
        include_technicals=args.scope in {"all", "prices"},
        include_ml=args.scope in {"all", "ml_training"},
    )
    report["recovery"] = recovery
    write_recovery_report(recovery, args.output)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["overall"] in {"fresh", "warning"} else 1

    print(f"overall={report['overall']}")
    print(f"daily_prices={report['daily_prices']['status']}")
    print(f"technical_features={report['technical_features']['status']}")
    print(f"market_regimes={report['market_regimes']['status']}")
    print(f"news_events={report['news_events']['status']}")
    print(f"ml_training_data={report['ml_training_data']['status']}")
    print(f"pipeline_last_run={report['pipeline_last_run']['status']}")
    if "fundamental_snapshots" in report:
        print(f"fundamental_snapshots={report['fundamental_snapshots']['status']}")
    findings_by_source = {
        finding["source"]: finding for finding in recovery.get("findings", [])
    }
    for warning in report["warnings"]:
        action = (findings_by_source.get(warning["source"], {}).get("recommended_action") or {})
        action_text = action.get("command") or action.get("id") or "manual_review"
        print(
            f"warning={warning['source']}:{warning['status']}:"
            f"{warning['message']} recommended_action={action_text}"
        )
    print(f"recovery_status={recovery['status']}")
    print(f"recovery_report_impact={recovery['report_impact']}")

    return 0 if report["overall"] in {"fresh", "warning"} else 1


def apply_scope(report: dict, scope: str) -> dict:
    if scope == "all":
        return report

    scoped_sources = {
        "prices": ["daily_prices", "technical_features", "market_regimes"],
        "ml_training": ["ml_training_data"],
    }[scope]
    statuses = [report[source]["status"] for source in scoped_sources]
    scoped_report = {
        **report,
        "scope_mode": scope,
        "overall": classify_scoped_overall(statuses),
        "warnings": [
            warning
            for warning in report.get("warnings", [])
            if warning.get("source") in scoped_sources
        ],
    }
    return scoped_report


def classify_scoped_overall(statuses: list[str]) -> str:
    if "missing" in statuses:
        return "missing"
    if "stale" in statuses:
        return "stale"
    if "warning" in statuses:
        return "warning"
    return "fresh"


def write_recovery_report(recovery: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(recovery, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
