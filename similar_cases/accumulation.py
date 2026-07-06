from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from similar_cases.engine import build_similar_case_query, find_similar_cases
from similar_cases.schema import SimilarCaseRecord


DEFAULT_MIN_SAMPLES = 5


def build_similar_case_result_rows(
    *,
    dataset_path: str | Path,
    ticker_metadata: list[dict] | None = None,
    universe: str = "QQQ100",
    latest_per_ticker: bool = True,
    max_queries: int | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    generated_at: datetime | None = None,
) -> dict:
    dataset = pd.read_csv(dataset_path)
    if dataset.empty:
        return build_result_payload(rows=[], dataset=dataset, generated_at=generated_at)

    dataset = prepare_dataset(dataset)
    metadata_by_ticker = {
        str(row.get("ticker", "")).upper(): row for row in (ticker_metadata or [])
    }
    query_rows = select_query_rows(
        dataset,
        latest_per_ticker=latest_per_ticker,
        max_queries=max_queries,
    )
    source_data_as_of = str(dataset["date"].max())[:10]
    generated = generated_at or datetime.now(UTC)
    output_rows = []

    for _, query_row in query_rows.iterrows():
        query_date = query_row["date"]
        history = dataset[dataset["date"] < query_date]
        records = [
            build_case_record(row, metadata_by_ticker=metadata_by_ticker, universe=universe)
            for _, row in history.iterrows()
        ]
        ticker = str(query_row["ticker"]).upper()
        metadata = metadata_by_ticker.get(ticker, {})
        technical_pattern = classify_technical_pattern(query_row)
        news_event_type = classify_news_event_type(query_row)
        market_regime = str(query_row.get("market_regime") or "unknown")
        query = build_similar_case_query(
            ticker=ticker,
            technical_pattern=technical_pattern,
            market_regime=market_regime,
            news_event_type=news_event_type,
            industry=metadata.get("industry"),
            market_cap_bucket=metadata.get("market_cap_bucket"),
            volatility_bucket=metadata.get("volatility_bucket"),
            universe=universe,
        )
        result = find_similar_cases(
            query=query,
            records=records,
            min_samples=min_samples,
        )
        output_rows.append(
            build_supabase_row(
                ticker=ticker,
                query_date=str(query_date)[:10],
                technical_pattern=technical_pattern,
                news_event_type=news_event_type,
                market_regime=market_regime,
                result=result,
                source_data_as_of=source_data_as_of,
                refreshed_at=generated.replace(microsecond=0).isoformat(),
            )
        )

    return build_result_payload(
        rows=output_rows,
        dataset=dataset,
        generated_at=generated,
    )


def prepare_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    prepared = dataset.copy()
    prepared["ticker"] = prepared["ticker"].astype(str).str.upper()
    prepared["date"] = pd.to_datetime(prepared["date"]).dt.date
    return prepared.sort_values(["ticker", "date"])


def select_query_rows(
    dataset: pd.DataFrame,
    *,
    latest_per_ticker: bool,
    max_queries: int | None,
) -> pd.DataFrame:
    if latest_per_ticker:
        query_rows = dataset.sort_values("date").groupby("ticker", as_index=False).tail(1)
    else:
        query_rows = dataset

    query_rows = query_rows.sort_values(["ticker", "date"])
    if max_queries is not None:
        query_rows = query_rows.head(max_queries)
    return query_rows


def build_case_record(
    row: pd.Series,
    *,
    metadata_by_ticker: dict[str, dict],
    universe: str,
) -> SimilarCaseRecord:
    ticker = str(row["ticker"]).upper()
    metadata = metadata_by_ticker.get(ticker, {})
    return SimilarCaseRecord(
        ticker=ticker,
        event_date=str(row["date"])[:10],
        technical_pattern=classify_technical_pattern(row),
        market_regime=str(row.get("market_regime") or "unknown"),
        themes=tuple(metadata.get("themes") or ()),
        industry=metadata.get("industry"),
        market_cap_bucket=metadata.get("market_cap_bucket"),
        volatility_bucket=metadata.get("volatility_bucket"),
        news_event_type=classify_news_event_type(row),
        universe=universe,
        forward_return_5d=safe_float(row.get("forward_return_5d")),
        forward_return_10d=safe_float(row.get("forward_return_10d")),
        forward_return_20d=safe_float(row.get("forward_return_20d")),
    )


def classify_technical_pattern(row: pd.Series) -> str:
    if to_bool(row.get("is_breakout")):
        return "breakout"
    if to_bool(row.get("is_volume_surge")):
        return "volume_surge"
    if to_bool(row.get("is_pullback")):
        return "pullback"

    price_vs_ma20 = safe_float(row.get("price_vs_ma20"))
    macd_histogram = safe_float(row.get("macd_histogram"))
    if price_vs_ma20 is not None and macd_histogram is not None:
        if price_vs_ma20 < 0 and macd_histogram < 0:
            return "below_ma20_negative_momentum"
        if price_vs_ma20 > 0 and macd_histogram > 0:
            return "above_ma20_positive_momentum"
    return "neutral"


def classify_news_event_type(row: pd.Series) -> str:
    if safe_float(row.get("risk_event_count_30d")) and safe_float(row.get("risk_event_count_30d")) > 0:
        return "risk_event"
    if (
        safe_float(row.get("earnings_guidance_count_30d"))
        and safe_float(row.get("earnings_guidance_count_30d")) > 0
    ):
        return "earnings_guidance"
    if (
        safe_float(row.get("product_demand_count_30d"))
        and safe_float(row.get("product_demand_count_30d")) > 0
    ):
        return "product_demand"
    if to_bool(row.get("news_missing")):
        return "no_recent_news"
    return "general"


def build_supabase_row(
    *,
    ticker: str,
    query_date: str,
    technical_pattern: str,
    news_event_type: str,
    market_regime: str,
    result: dict,
    source_data_as_of: str,
    refreshed_at: str,
) -> dict:
    summary = result["summary"]
    return {
        "query_ticker": ticker.upper(),
        "query_date": query_date,
        "scope": result["scope"],
        "relaxation_step": result["relaxation_step"],
        "matched_fields": result["matched_fields"],
        "technical_pattern": technical_pattern,
        "news_event_type": news_event_type,
        "market_regime": market_regime,
        "sample_size": summary["sample_size"],
        "win_rate_5d": summary["win_rate_5d"],
        "win_rate_10d": summary["win_rate_10d"],
        "win_rate_20d": summary["win_rate_20d"],
        "average_forward_return_20d": summary["average_forward_return_20d"],
        "max_loss_20d": summary["max_loss_20d"],
        "evidence_quality": summary["evidence_quality"],
        "source_data_as_of": source_data_as_of,
        "result_status": "fresh" if result["status"] == "success" else "missing",
        "refreshed_at": refreshed_at,
    }


def build_result_payload(
    *,
    rows: list[dict],
    dataset: pd.DataFrame,
    generated_at: datetime | None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    return {
        "status": "success",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "dataset_rows": int(len(dataset)),
        "result_rows": rows,
        "result_count": len(rows),
        "fresh_count": sum(1 for row in rows if row["result_status"] == "fresh"),
        "missing_count": sum(1 for row in rows if row["result_status"] == "missing"),
    }


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}
