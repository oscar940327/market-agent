import re
from datetime import date

from agent.fixed_single_stock_report import build_decision
from agent.report_context import build_single_stock_report_context


OUTCOME_HORIZONS = (5, 10, 20)
TRACKED_INTENTS = {"single_stock_analysis", "industry_trend"}
SKIPPED_OUTCOME_INTENTS = {"backtest_query"}


def build_research_log_row(
    *,
    query: str,
    intent: str,
    data: dict,
    report: str,
    request_options: dict | None = None,
    output_snapshot: dict | None = None,
) -> dict:
    ticker = normalize_ticker(data.get("ticker"))
    profile = data.get("research_profile") or {}
    price_plan = profile.get("price_plan") or {}
    tracking = build_tracking_summary(intent=intent, data=data)

    return {
        "query": query,
        "intent": intent,
        "ticker": ticker,
        "theme": data.get("theme_key") or data.get("theme"),
        "workflow_kind": classify_workflow_kind(intent),
        "decision": tracking.get("conclusion") or price_plan.get("decision") or profile.get("decision"),
        "conclusion": tracking.get("conclusion"),
        "valuation_label": tracking.get("valuation_label"),
        "technical_label": tracking.get("technical_label"),
        "news_sentiment": tracking.get("news_sentiment"),
        "ml_reference_status": tracking.get("ml_reference_status"),
        "ml_reference_trust_status": tracking.get("ml_reference_trust_status"),
        "data_freshness_status": tracking.get("data_freshness_status"),
        "exit_signal": tracking.get("exit_signal"),
        "research_signal_score": tracking.get("research_signal_score"),
        "evidence_quality": normalize_evidence_quality(data.get("evidence_quality")),
        "price_at_query": extract_price_at_query(data),
        "data_as_of": extract_data_as_of(data),
        "report_summary": summarize_report(report),
        "request_options": request_options or {},
        "output_snapshot": output_snapshot or data,
        "price_plan": tracking.get("price_plan") or price_plan or {},
        "tracking_status": tracking.get("tracking_status"),
        "tracked_tickers": tracking.get("tracked_tickers"),
        "tracking_notes": tracking.get("tracking_notes"),
    }


def build_pending_outcome_rows(
    *,
    research_log_id: str,
    ticker: str,
    query_date: date,
    price_at_query: float | None,
    price_provider: str = "yfinance",
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
    intent: str | None = None,
    theme: str | None = None,
    conclusion: str | None = None,
    exit_signal: str | None = None,
    price_plan: dict | None = None,
    outcome_status: str = "pending",
    tracking_notes: str | None = None,
) -> list[dict]:
    return [
        {
            "research_log_id": research_log_id,
            "ticker": ticker.upper(),
            "query_date": query_date.isoformat(),
            "intent": intent,
            "theme": theme,
            "conclusion": conclusion,
            "exit_signal": exit_signal,
            "horizon_trading_days": horizon,
            "target_date": None,
            "actual_date": None,
            "price_at_query": price_at_query,
            "price_at_horizon": None,
            "return_pct": None,
            "max_drawdown_pct": None,
            "max_runup_pct": None,
            "entry_touched": None,
            "exit_touched": None,
            "stop_loss_touched": None,
            "outcome_status": outcome_status,
            "price_provider": price_provider,
            "price_plan": price_plan or {},
            "tracking_notes": tracking_notes,
            "used_for_calibration": False,
            "calibration_notes": None,
            "computed_at": None,
        }
        for horizon in horizons
    ]


def build_research_outcome_rows_for_data(
    *,
    research_log_id: str,
    data: dict,
    query_date: date,
    intent: str,
    price_provider: str = "yfinance",
) -> list[dict]:
    tracking = build_tracking_summary(intent=intent, data=data)
    status = "pending" if intent in TRACKED_INTENTS else "skipped"
    tickers = tracking["tracked_tickers"]

    if not tickers:
        return []

    rows = []
    for ticker in tickers:
        rows.extend(
            build_pending_outcome_rows(
                research_log_id=research_log_id,
                ticker=ticker,
                query_date=query_date,
                price_at_query=extract_price_for_ticker(data, ticker),
                price_provider=price_provider,
                intent=intent,
                theme=data.get("theme_key") or data.get("theme"),
                conclusion=tracking.get("conclusion"),
                exit_signal=tracking.get("exit_signal"),
                price_plan=extract_price_plan_for_ticker(data, ticker),
                outcome_status=status,
                tracking_notes=tracking.get("tracking_notes"),
            )
        )

    return rows


def build_tracking_summary(*, intent: str, data: dict) -> dict:
    if intent == "single_stock_analysis" and data.get("status") == "success":
        context = build_single_stock_report_context(data)
        decision = build_decision(context)
        ticker = normalize_ticker(data.get("ticker"))
        return {
            "tracking_status": "tracked" if ticker else "no_ticker",
            "tracked_tickers": [ticker] if ticker else [],
            "tracking_notes": "single_stock_research_tracked",
            "conclusion": decision["conclusion"],
            "valuation_label": decision["valuation"],
            "technical_label": decision["technical"],
            "news_sentiment": (context.get("news_summary") or {}).get("sentiment"),
            "ml_reference_status": (context.get("ml_research") or {}).get("status"),
            "ml_reference_trust_status": (context.get("ml_reference_trust") or {}).get("status"),
            "data_freshness_status": (context.get("data_freshness") or {}).get("overall"),
            "exit_signal": (context.get("exit_signal") or {}).get("exit_signal"),
            "research_signal_score": (context.get("research_profile") or {}).get("combined_score"),
            "price_plan": (context.get("research_profile") or {}).get("price_plan") or {},
        }

    if intent == "industry_trend" and data.get("status") == "success":
        tickers = [
            normalize_ticker(item.get("ticker"))
            for item in data.get("results", [])
            if item.get("status") == "success" and item.get("ticker")
        ]
        tickers = [ticker for ticker in tickers if ticker]
        sector_summary = data.get("sector_summary") or {}
        ml_reference = data.get("theme_ml_reference") or data.get("ml_research") or {}
        return {
            "tracking_status": "tracked" if tickers else "no_successful_tickers",
            "tracked_tickers": tickers,
            "tracking_notes": "theme_constituent_outcomes_tracked",
            "conclusion": sector_summary.get("breadth_label"),
            "valuation_label": None,
            "technical_label": sector_summary.get("breadth_label"),
            "news_sentiment": None,
            "ml_reference_status": ml_reference.get("status"),
            "ml_reference_trust_status": (data.get("theme_ml_reference_trust") or {}).get("status"),
            "data_freshness_status": (data.get("data_freshness") or {}).get("overall"),
            "exit_signal": None,
            "research_signal_score": sector_summary.get("average_score"),
            "price_plan": {},
        }

    if intent == "backtest_query":
        ticker = normalize_ticker(data.get("ticker"))
        return {
            "tracking_status": "skipped",
            "tracked_tickers": [ticker] if ticker else [],
            "tracking_notes": "backtest_query_is_historical_and_not_forward_tracked",
            "conclusion": (data.get("evidence_quality") or {}).get("level"),
            "valuation_label": None,
            "technical_label": data.get("strategy"),
            "news_sentiment": None,
            "ml_reference_status": "not_applicable",
            "ml_reference_trust_status": "not_applicable",
            "data_freshness_status": None,
            "exit_signal": None,
            "research_signal_score": None,
            "price_plan": {},
        }

    return {
        "tracking_status": "skipped",
        "tracked_tickers": [],
        "tracking_notes": f"{intent}_not_supported_for_research_outcome_tracking",
        "price_plan": {},
    }


def classify_workflow_kind(intent: str) -> str:
    if intent == "industry_trend":
        return "theme"
    if intent == "backtest_query":
        return "backtest"
    if intent == "portfolio_analysis":
        return "portfolio"
    return "single_stock"


def normalize_ticker(ticker: str | None) -> str | None:
    return ticker.upper() if ticker else None


def normalize_evidence_quality(value) -> str | None:
    if isinstance(value, dict):
        return value.get("overall") or value.get("level") or value.get("quality")

    if isinstance(value, str):
        return value

    return None


def extract_price_at_query(data: dict) -> float | None:
    technical = data.get("technical_analysis") or {}
    current_price = technical.get("current_price")

    if current_price is not None:
        return float(current_price)

    profile = data.get("research_profile") or {}
    price_plan = profile.get("price_plan") or {}
    reference_price = price_plan.get("reference_price")

    return float(reference_price) if reference_price is not None else None


def extract_price_for_ticker(data: dict, ticker: str) -> float | None:
    if normalize_ticker(data.get("ticker")) == normalize_ticker(ticker):
        return extract_price_at_query(data)

    for result in data.get("results", []):
        if normalize_ticker(result.get("ticker")) != normalize_ticker(ticker):
            continue
        analysis = result.get("analysis") or {}
        return extract_price_at_query(analysis)

    return None


def extract_price_plan_for_ticker(data: dict, ticker: str) -> dict:
    if normalize_ticker(data.get("ticker")) == normalize_ticker(ticker):
        return normalize_price_plan((data.get("research_profile") or {}).get("price_plan") or {})

    for result in data.get("results", []):
        if normalize_ticker(result.get("ticker")) != normalize_ticker(ticker):
            continue
        analysis = result.get("analysis") or {}
        profile = analysis.get("research_profile") or {}
        return normalize_price_plan(profile.get("price_plan") or {})

    return {}


def normalize_price_plan(price_plan: dict) -> dict:
    if not isinstance(price_plan, dict):
        return {}

    return {
        key: value
        for key, value in price_plan.items()
        if value is not None
    }


def extract_data_as_of(data: dict) -> str | None:
    data_window = data.get("data_window") or {}
    if data_window.get("data_as_of"):
        return data_window["data_as_of"]

    technical = data.get("technical_analysis") or {}
    return technical.get("data_as_of")


def extract_ticker_from_query(user_query: str) -> str | None:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())
    return candidates[0] if candidates else None


def summarize_report(report: str, max_chars: int = 1000) -> str:
    cleaned = " ".join(report.split())
    return cleaned[:max_chars]
