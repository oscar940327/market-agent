import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.reporting import build_report  # noqa: E402
from data_store.supabase_store import insert_research_log, upsert_research_outcomes  # noqa: E402
from main import run_single_stock_analysis  # noqa: E402
from research_logging import build_pending_outcome_rows, build_research_log_row  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and log one research result.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--analyst-mode", default="rule_based")
    parser.add_argument("--include-news", action="store_true", default=True)
    parser.add_argument("--exclude-news", action="store_false", dest="include_news")
    parser.add_argument("--include-fundamentals", action="store_true", default=True)
    parser.add_argument(
        "--exclude-fundamentals",
        action="store_false",
        dest="include_fundamentals",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    data = run_single_stock_analysis(
        ticker=ticker,
        user_query=args.query,
        include_news=args.include_news,
        include_fundamentals=args.include_fundamentals,
    )
    report_result = build_report(
        kind="single_stock",
        data=data,
        analyst_mode=args.analyst_mode,
    )
    request_options = {
        "include_news": args.include_news,
        "include_fundamentals": args.include_fundamentals,
        "include_technicals": True,
        "analyst_mode": args.analyst_mode,
    }
    log_row = build_research_log_row(
        query=args.query,
        intent="single_stock_analysis",
        data=data,
        report=report_result["report"],
        request_options=request_options,
        output_snapshot={
            "data": data,
            "analyst": report_result["analyst"],
        },
    )
    log_result = insert_research_log(log_row)
    print(f"research_log={log_result['status']}")

    if log_result["status"] != "success":
        print(f"message={log_result.get('message')}")
        return 1

    research_log = log_result["row"]
    outcome_rows = []
    if log_row.get("ticker"):
        outcome_rows = build_pending_outcome_rows(
            research_log_id=research_log["id"],
            ticker=log_row["ticker"],
            query_date=date.today(),
            price_at_query=log_row.get("price_at_query"),
        )
        outcome_result = upsert_research_outcomes(outcome_rows)
        print(f"research_outcomes={outcome_result['status']}")
        print(f"research_outcomes_upserted={outcome_result['upserted_count']}")

        if outcome_result["status"] != "success":
            print(f"message={outcome_result.get('message')}")
            return 1

    print(f"research_log_id={research_log['id']}")
    print(f"ticker={log_row.get('ticker')}")
    print(f"pending_outcomes={len(outcome_rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
