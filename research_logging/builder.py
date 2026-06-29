from datetime import date


OUTCOME_HORIZONS = (5, 10, 20)


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

    return {
        "query": query,
        "intent": intent,
        "ticker": ticker,
        "theme": data.get("theme"),
        "decision": price_plan.get("decision") or profile.get("decision"),
        "evidence_quality": normalize_evidence_quality(data.get("evidence_quality")),
        "price_at_query": extract_price_at_query(data),
        "data_as_of": extract_data_as_of(data),
        "report_summary": summarize_report(report),
        "request_options": request_options or {},
        "output_snapshot": output_snapshot or data,
    }


def build_pending_outcome_rows(
    *,
    research_log_id: str,
    ticker: str,
    query_date: date,
    price_at_query: float | None,
    price_provider: str = "yfinance",
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
) -> list[dict]:
    return [
        {
            "research_log_id": research_log_id,
            "ticker": ticker.upper(),
            "query_date": query_date.isoformat(),
            "horizon_trading_days": horizon,
            "target_date": None,
            "actual_date": None,
            "price_at_query": price_at_query,
            "price_at_horizon": None,
            "return_pct": None,
            "max_drawdown_pct": None,
            "max_runup_pct": None,
            "outcome_status": "pending",
            "price_provider": price_provider,
            "used_for_calibration": False,
            "calibration_notes": None,
            "computed_at": None,
        }
        for horizon in horizons
    ]


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


def extract_data_as_of(data: dict) -> str | None:
    data_window = data.get("data_window") or {}
    if data_window.get("data_as_of"):
        return data_window["data_as_of"]

    technical = data.get("technical_analysis") or {}
    return technical.get("data_as_of")


def summarize_report(report: str, max_chars: int = 1000) -> str:
    cleaned = " ".join(report.split())
    return cleaned[:max_chars]
