import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_freshness import build_current_data_freshness  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Market Agent data freshness.")
    parser.add_argument("--ticker", default="QQQ")
    parser.add_argument("--benchmark", default="QQQ")
    parser.add_argument(
        "--scope",
        choices=["all", "prices"],
        default="all",
        help="Use prices to evaluate only market data freshness.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_current_data_freshness(
        ticker=args.ticker,
        benchmark=args.benchmark,
    )
    report = apply_scope(report, args.scope)

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
    for warning in report["warnings"]:
        print(
            f"warning={warning['source']}:{warning['status']}:"
            f"{warning['message']}"
        )

    return 0 if report["overall"] in {"fresh", "warning"} else 1


def apply_scope(report: dict, scope: str) -> dict:
    if scope == "all":
        return report

    scoped_sources = {
        "prices": ["daily_prices", "technical_features", "market_regimes"],
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


if __name__ == "__main__":
    raise SystemExit(main())
