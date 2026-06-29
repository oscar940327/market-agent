import calendar
import csv
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from data_providers.price_service import PriceFetchResult, fetch_price_data_range


RESEARCH_YEARS = 15
BUFFER_MONTHS = 2
MIN_TRADING_DAYS_FOR_FULL_HISTORY = 252 * RESEARCH_YEARS - 30


@dataclass
class PriceIngestPlan:
    data_end_date: date
    research_start_date: date
    fetch_start_date: date
    research_years: int = RESEARCH_YEARS
    buffer_months: int = BUFFER_MONTHS


@dataclass
class PriceIngestResult:
    ticker: str
    status: str
    provider: str | None
    attempted_providers: list[str]
    records: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    data_start_date: str | None = None
    data_end_date: str | None = None
    research_start_date: str | None = None
    fetch_start_date: str | None = None
    row_count: int = 0
    trading_days_in_research_window: int = 0
    insufficient_reason: str | None = None
    history_note: str | None = None


def build_price_ingest_plan(
    *,
    data_end_date: date | None = None,
    research_years: int = RESEARCH_YEARS,
    buffer_months: int = BUFFER_MONTHS,
) -> PriceIngestPlan:
    resolved_end_date = data_end_date or date.today()
    research_start_date = subtract_years_months(
        resolved_end_date,
        years=research_years,
    )
    fetch_start_date = subtract_years_months(
        research_start_date,
        months=buffer_months,
    )

    return PriceIngestPlan(
        data_end_date=resolved_end_date,
        research_start_date=research_start_date,
        fetch_start_date=fetch_start_date,
        research_years=research_years,
        buffer_months=buffer_months,
    )


def fetch_daily_price_history(
    *,
    ticker: str,
    plan: PriceIngestPlan,
    providers: tuple[str, ...] = ("yfinance", "stooq"),
) -> PriceIngestResult:
    fetch_result = fetch_price_data_range(
        ticker=ticker,
        start_date=plan.fetch_start_date.isoformat(),
        end_date=add_days(plan.data_end_date, 1).isoformat(),
        providers=providers,
    )

    return build_price_ingest_result(
        ticker=ticker,
        fetch_result=fetch_result,
        plan=plan,
    )


def build_price_ingest_result(
    *,
    ticker: str,
    fetch_result: PriceFetchResult,
    plan: PriceIngestPlan,
) -> PriceIngestResult:
    if not fetch_result.is_success:
        return PriceIngestResult(
            ticker=ticker.upper(),
            status="no_price_data",
            provider=None,
            attempted_providers=fetch_result.attempted_providers,
            errors=fetch_result.errors,
            research_start_date=plan.research_start_date.isoformat(),
            fetch_start_date=plan.fetch_start_date.isoformat(),
        )

    normalized_data = normalize_price_frame(fetch_result.data)
    if normalized_data.empty:
        return PriceIngestResult(
            ticker=ticker.upper(),
            status="no_price_data",
            provider=fetch_result.provider,
            attempted_providers=fetch_result.attempted_providers,
            errors=fetch_result.errors,
            research_start_date=plan.research_start_date.isoformat(),
            fetch_start_date=plan.fetch_start_date.isoformat(),
        )

    records = build_daily_price_records(
        ticker=ticker,
        provider=fetch_result.provider,
        price_data=normalized_data,
    )
    first_date = normalized_data.index.min().date()
    last_date = normalized_data.index.max().date()
    research_window_data = normalized_data[
        normalized_data.index.date >= plan.research_start_date
    ]
    status = classify_price_history_status(
        first_date=first_date,
        trading_days_in_research_window=len(research_window_data),
        plan=plan,
    )
    insufficient_reason = classify_insufficient_reason(
        first_date=first_date,
        status=status,
        trading_days_in_research_window=len(research_window_data),
        plan=plan,
    )
    history_note = build_history_note(insufficient_reason)

    return PriceIngestResult(
        ticker=ticker.upper(),
        status=status,
        provider=fetch_result.provider,
        attempted_providers=fetch_result.attempted_providers,
        records=records,
        errors=fetch_result.errors,
        data_start_date=first_date.isoformat(),
        data_end_date=last_date.isoformat(),
        research_start_date=plan.research_start_date.isoformat(),
        fetch_start_date=plan.fetch_start_date.isoformat(),
        row_count=len(records),
        trading_days_in_research_window=len(research_window_data),
        insufficient_reason=insufficient_reason,
        history_note=history_note,
    )


def normalize_price_frame(price_data: pd.DataFrame) -> pd.DataFrame:
    if price_data is None or price_data.empty:
        return pd.DataFrame()

    normalized = price_data.copy()
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()

    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    missing_columns = [column for column in required_columns if column not in normalized]
    if missing_columns:
        return pd.DataFrame()

    return normalized


def build_daily_price_records(
    *,
    ticker: str,
    provider: str,
    price_data: pd.DataFrame,
) -> list[dict]:
    records = []
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    for index, row in price_data.iterrows():
        records.append(
            {
                "ticker": ticker.upper(),
                "date": index.date().isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "adj_close": (
                    float(row["Adj Close"]) if "Adj Close" in row and pd.notna(row["Adj Close"]) else None
                ),
                "volume": float(row["Volume"]),
                "provider": provider,
                "fetched_at": fetched_at,
            }
        )

    return records


def classify_price_history_status(
    *,
    first_date: date,
    trading_days_in_research_window: int,
    plan: PriceIngestPlan,
) -> str:
    if first_date > plan.research_start_date:
        return "insufficient_history"

    if trading_days_in_research_window < MIN_TRADING_DAYS_FOR_FULL_HISTORY:
        return "partial_history"

    return "success"


def classify_insufficient_reason(
    *,
    first_date: date,
    status: str,
    trading_days_in_research_window: int,
    plan: PriceIngestPlan,
) -> str | None:
    if status == "success":
        return None

    if first_date > plan.research_start_date:
        return "listed_after_research_start"

    if trading_days_in_research_window < MIN_TRADING_DAYS_FOR_FULL_HISTORY:
        return "provider_history_short"

    return "unknown"


def build_history_note(insufficient_reason: str | None) -> str | None:
    if insufficient_reason == "listed_after_research_start":
        return "目前 ticker 無 15 年價格資料"

    if insufficient_reason == "provider_history_short":
        return "provider 回傳歷史資料不足"

    if insufficient_reason == "unknown":
        return "不足原因待確認"

    return None


def write_price_ingest_report(
    *,
    results: list[PriceIngestResult],
    output_dir: str | Path = "data/market/prices",
    report_date: str | None = None,
) -> tuple[Path, Path]:
    date_label = report_date or date.today().isoformat()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / f"price_ingest_report_{date_label}.csv"
    missing_path = output_path / f"missing_price_data_{date_label}.csv"
    fieldnames = [
        "ticker",
        "status",
        "provider",
        "attempted_providers",
        "row_count",
        "trading_days_in_research_window",
        "insufficient_reason",
        "history_note",
        "data_start_date",
        "data_end_date",
        "research_start_date",
        "fetch_start_date",
        "errors",
    ]

    with report_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result_to_report_row(result))

    with missing_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            if should_include_in_missing_price_report(result):
                writer.writerow(result_to_report_row(result))

    return report_path, missing_path


def should_include_in_missing_price_report(result: PriceIngestResult) -> bool:
    if result.status == "success":
        return False

    if result.insufficient_reason == "listed_after_research_start":
        return False

    return True


def result_to_report_row(result: PriceIngestResult) -> dict:
    return {
        "ticker": result.ticker,
        "status": result.status,
        "provider": result.provider or "",
        "attempted_providers": ";".join(result.attempted_providers),
        "row_count": result.row_count,
        "trading_days_in_research_window": result.trading_days_in_research_window,
        "insufficient_reason": result.insufficient_reason or "",
        "history_note": result.history_note or "",
        "data_start_date": result.data_start_date or "",
        "data_end_date": result.data_end_date or "",
        "research_start_date": result.research_start_date or "",
        "fetch_start_date": result.fetch_start_date or "",
        "errors": " | ".join(error.get("message", "") for error in result.errors),
    }


def subtract_years_months(
    source_date: date,
    *,
    years: int = 0,
    months: int = 0,
) -> date:
    target_year = source_date.year - years
    target_month = source_date.month - months

    while target_month <= 0:
        target_month += 12
        target_year -= 1

    max_day = calendar.monthrange(target_year, target_month)[1]
    return source_date.replace(
        year=target_year,
        month=target_month,
        day=min(source_date.day, max_day),
    )


def add_days(source_date: date, days: int) -> date:
    return source_date + timedelta(days=days)
