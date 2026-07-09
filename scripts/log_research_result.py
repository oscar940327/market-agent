import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.reporting import build_report  # noqa: E402
from agent.rule_based_router import detect_intent  # noqa: E402
from data_store.supabase_store import insert_research_log, upsert_research_outcomes  # noqa: E402
from main import run_backtest_query, run_single_stock_analysis, run_theme_analysis  # noqa: E402
from research_logging import (  # noqa: E402
    build_research_log_row,
    build_research_outcome_rows_for_data,
)
from research_logging.builder import extract_ticker_from_query  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and log one research result.")
    parser.add_argument("--ticker")
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
    parser.add_argument("--skip-outcomes", action="store_true")
    args = parser.parse_args()

    route = detect_intent(args.query)
    intent = route["intent"]
    data, report_kind = run_research_workflow(args=args, intent=intent)

    if data.get("status") != "success":
        print(f"status={data.get('status')}")
        print(f"message={data.get('message')}")
        return 1

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
    }
    log_row = build_research_log_row(
        query=args.query,
        intent=intent,
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
    if not args.skip_outcomes:
        outcome_rows = build_research_outcome_rows_for_data(
            research_log_id=research_log["id"],
            data=data,
            query_date=date.today(),
            intent=intent,
        )

    if outcome_rows:
        outcome_result = upsert_research_outcomes(outcome_rows)
        print(f"research_outcomes={outcome_result['status']}")
        print(f"research_outcomes_upserted={outcome_result['upserted_count']}")

        if outcome_result["status"] != "success":
            print(f"message={outcome_result.get('message')}")
            return 1

    print(f"research_log_id={research_log['id']}")
    print(f"ticker={log_row.get('ticker')}")
    print(f"intent={intent}")
    print(f"tracking_status={log_row.get('tracking_status')}")
    print(f"tracked_tickers={','.join(log_row.get('tracked_tickers') or [])}")
    print(f"pending_outcomes={len(outcome_rows)}")

    return 0


def run_research_workflow(*, args: argparse.Namespace, intent: str) -> tuple[dict, str]:
    ticker = (args.ticker or extract_ticker_from_query(args.query) or "").upper()

    if intent == "single_stock_analysis":
        if not ticker:
            return (
                {
                    "status": "needs_ticker",
                    "intent": intent,
                    "query": args.query,
                    "message": "這類問題需要 ticker 才能記錄 research outcome。",
                },
                "single_stock",
            )
        return (
            run_single_stock_analysis(
                ticker=ticker,
                user_query=args.query,
                include_news=args.include_news,
                include_fundamentals=args.include_fundamentals,
            ),
            "single_stock",
        )

    if intent == "industry_trend":
        return run_theme_analysis(args.query), "theme"

    if intent == "backtest_query":
        if not ticker:
            return (
                {
                    "status": "needs_ticker",
                    "intent": intent,
                    "query": args.query,
                    "message": "回測問題需要 ticker 才能記錄 research log。",
                },
                "backtest",
            )
        return run_backtest_query(ticker=ticker, user_query=args.query), "backtest"

    return (
        {
            "status": "unsupported_intent",
            "intent": intent,
            "query": args.query,
            "message": "目前這個 intent 尚未支援 research outcome logging。",
        },
        "single_stock",
    )


if __name__ == "__main__":
    raise SystemExit(main())
