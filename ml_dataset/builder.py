import csv
import json
import math
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ml_versions import FEATURE_VERSION, LABEL_VERSION

SPLIT_RANGES = {
    "train": (date(2011, 1, 1), date(2020, 12, 31)),
    "validation": (date(2021, 1, 1), date(2022, 12, 31)),
    "test": (date(2023, 1, 1), None),
}

FEATURE_COLUMNS = [
    "price_vs_ma5",
    "price_vs_ma10",
    "price_vs_ma20",
    "price_vs_ma50",
    "price_vs_ma200",
    "ma5_vs_ma20",
    "ma20_vs_ma50",
    "ma50_vs_ma200",
    "rsi_14",
    "macd",
    "macd_histogram",
    "is_breakout",
    "is_volume_surge",
    "is_pullback",
    "return_5d",
    "return_10d",
    "return_20d",
    "volatility_20d",
    "volume_ratio_20d",
    "market_regime",
    "qqq_above_ma200",
    "qqq_return_20d",
    "qqq_return_60d",
    "regime_changed",
    "news_count_30d",
    "news_sentiment_score_30d",
    "high_importance_news_count_30d",
    "risk_event_count_30d",
    "earnings_guidance_count_30d",
    "product_demand_count_30d",
    "days_since_last_news",
    "news_missing",
    "similar_case_sample_size",
    "similar_case_win_rate_5d",
    "similar_case_win_rate_10d",
    "similar_case_win_rate_20d",
    "similar_case_average_return_20d",
    "similar_case_max_loss_20d",
    "similar_case_evidence_quality",
]

LABEL_COLUMNS = [
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "up_5d",
    "up_10d",
    "up_20d",
    "non_upside_5d",
    "non_upside_10d",
    "non_upside_20d",
    "large_drop_20d",
    "max_drop_20d",
    "expected_return_range_5d",
    "expected_return_range_10d",
    "expected_return_range_20d",
    "historical_average_return_5d",
    "historical_average_return_10d",
    "historical_average_return_20d",
    "breakout_success_20d",
    "pullback_success_20d",
    "volume_surge_success_20d",
]

BASE_COLUMNS = [
    "ticker",
    "date",
    "split",
    "feature_version",
    "label_version",
    "data_as_of",
]


def build_training_dataset(
    *,
    tickers: list[str],
    daily_price_rows_by_ticker: dict[str, list[dict]],
    technical_rows_by_ticker: dict[str, list[dict]],
    market_regime_rows: list[dict],
    news_event_rows_by_ticker: dict[str, list[dict]] | None = None,
    similar_case_rows_by_ticker: dict[str, list[dict]] | None = None,
    universe: str = "QQQ100",
    feature_version: str = FEATURE_VERSION,
    label_version: str = LABEL_VERSION,
    generated_at: str | None = None,
) -> dict:
    generated_at = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    news_event_rows_by_ticker = news_event_rows_by_ticker or {}
    similar_case_rows_by_ticker = similar_case_rows_by_ticker or {}

    market_by_date = build_market_features_by_date(market_regime_rows)
    rows = []
    excluded_reasons = Counter()

    for ticker in [value.upper() for value in tickers]:
        price_rows = normalize_price_rows(daily_price_rows_by_ticker.get(ticker, []))
        price_index = {row["date"]: index for index, row in enumerate(price_rows)}
        technical_rows = normalize_rows_by_date(
            technical_rows_by_ticker.get(ticker, [])
        )
        news_rows = normalize_news_rows(news_event_rows_by_ticker.get(ticker, []))
        similar_rows = normalize_similar_case_rows(
            similar_case_rows_by_ticker.get(ticker, [])
        )

        for technical_row in technical_rows:
            row_date = technical_row["date"]
            split = classify_split(row_date)
            if split is None:
                excluded_reasons["outside_split_range"] += 1
                continue

            if row_date not in price_index:
                excluded_reasons["missing_price_row"] += 1
                continue

            market_features = market_by_date.get(row_date)
            if not market_features:
                excluded_reasons["missing_market_regime"] += 1
                continue

            technical_features = build_technical_features(
                technical_row=technical_row,
                price_rows=price_rows,
                price_index=price_index[row_date],
            )
            if technical_features is None:
                excluded_reasons["missing_core_technical_features"] += 1
                continue

            labels = build_labels(
                technical_row=technical_row,
                price_rows=price_rows,
                price_index=price_index[row_date],
            )
            if labels is None:
                excluded_reasons["missing_forward_labels"] += 1
                continue

            news_features = build_news_features(
                news_rows=news_rows,
                row_date=row_date,
            )
            similar_features = build_similar_case_features(
                similar_rows=similar_rows,
                row_date=row_date,
            )

            rows.append(
                {
                    "ticker": ticker,
                    "date": row_date.isoformat(),
                    "split": split,
                    "feature_version": feature_version,
                    "label_version": label_version,
                    "data_as_of": row_date.isoformat(),
                    **technical_features,
                    **market_features,
                    **news_features,
                    **similar_features,
                    **labels,
                }
            )

    rows = sorted(rows, key=lambda row: (row["ticker"], row["date"]))
    metadata = build_metadata(
        rows=rows,
        universe=universe,
        feature_version=feature_version,
        label_version=label_version,
        generated_at=generated_at,
        excluded_reasons=excluded_reasons,
    )
    return {"rows": rows, "metadata": metadata}


def build_technical_features(
    *,
    technical_row: dict,
    price_rows: list[dict],
    price_index: int,
) -> dict | None:
    close = safe_float(technical_row.get("close"))
    volume = safe_float(technical_row.get("volume"))
    ma5 = safe_float(technical_row.get("ma5"))
    ma10 = safe_float(technical_row.get("ma10"))
    ma20 = safe_float(technical_row.get("ma20"))
    ma50 = safe_float(technical_row.get("ma50"))
    ma200 = safe_float(technical_row.get("ma200"))
    rsi_14 = safe_float(technical_row.get("rsi_14"))
    macd = safe_float(technical_row.get("macd"))
    macd_histogram = safe_float(technical_row.get("macd_histogram"))

    core_values = [
        close,
        volume,
        ma5,
        ma10,
        ma20,
        ma50,
        ma200,
        rsi_14,
        macd,
        macd_histogram,
    ]
    if any(value is None for value in core_values):
        return None

    return_5d = trailing_return(price_rows, price_index, 5)
    return_10d = trailing_return(price_rows, price_index, 10)
    return_20d = trailing_return(price_rows, price_index, 20)
    volatility_20d = trailing_volatility(price_rows, price_index, 20)
    volume_ratio_20d = trailing_volume_ratio(price_rows, price_index, 20)
    if any(
        value is None
        for value in [
            return_5d,
            return_10d,
            return_20d,
            volatility_20d,
            volume_ratio_20d,
        ]
    ):
        return None

    return {
        "price_vs_ma5": ratio_delta(close, ma5),
        "price_vs_ma10": ratio_delta(close, ma10),
        "price_vs_ma20": ratio_delta(close, ma20),
        "price_vs_ma50": ratio_delta(close, ma50),
        "price_vs_ma200": ratio_delta(close, ma200),
        "ma5_vs_ma20": ratio_delta(ma5, ma20),
        "ma20_vs_ma50": ratio_delta(ma20, ma50),
        "ma50_vs_ma200": ratio_delta(ma50, ma200),
        "rsi_14": rsi_14,
        "macd": macd,
        "macd_histogram": macd_histogram,
        "is_breakout": bool(technical_row.get("is_breakout")),
        "is_volume_surge": bool(technical_row.get("is_volume_surge")),
        "is_pullback": bool(technical_row.get("is_pullback")),
        "return_5d": return_5d,
        "return_10d": return_10d,
        "return_20d": return_20d,
        "volatility_20d": volatility_20d,
        "volume_ratio_20d": volume_ratio_20d,
    }


def build_market_features_by_date(market_rows: list[dict]) -> dict[date, dict]:
    rows = normalize_rows_by_date(market_rows)
    rows_by_date = {}
    for index, row in enumerate(rows):
        close = safe_float(row.get("close"))
        ma200 = safe_float(row.get("ma200"))
        rows_by_date[row["date"]] = {
            "market_regime": row.get("regime") or "unknown",
            "qqq_above_ma200": (
                None if close is None or ma200 is None else bool(close > ma200)
            ),
            "qqq_return_20d": trailing_return(rows, index, 20),
            "qqq_return_60d": trailing_return(rows, index, 60),
            "regime_changed": bool(row.get("regime_changed")),
        }
    return {
        row_date: features
        for row_date, features in rows_by_date.items()
        if features["qqq_above_ma200"] is not None
        and features["qqq_return_20d"] is not None
        and features["qqq_return_60d"] is not None
    }


def build_news_features(*, news_rows: list[dict], row_date: date) -> dict:
    start_date = row_date - timedelta(days=30)
    matching_rows = [
        row
        for row in news_rows
        if row["published_date"] is not None
        and start_date <= row["published_date"] <= row_date
    ]
    if not matching_rows:
        return {
            "news_count_30d": 0,
            "news_sentiment_score_30d": 0.0,
            "high_importance_news_count_30d": 0,
            "risk_event_count_30d": 0,
            "earnings_guidance_count_30d": 0,
            "product_demand_count_30d": 0,
            "days_since_last_news": None,
            "news_missing": True,
        }

    sentiment_score = sum(score_news_sentiment(row.get("sentiment")) for row in matching_rows)
    latest_news_date = max(row["published_date"] for row in matching_rows)
    return {
        "news_count_30d": len(matching_rows),
        "news_sentiment_score_30d": sentiment_score / len(matching_rows),
        "high_importance_news_count_30d": count_matching(
            matching_rows, "importance", "high"
        ),
        "risk_event_count_30d": count_matching(matching_rows, "topic", "risk_event"),
        "earnings_guidance_count_30d": count_matching(
            matching_rows, "topic", "earnings_guidance"
        ),
        "product_demand_count_30d": count_matching(
            matching_rows, "topic", "product_demand"
        ),
        "days_since_last_news": (row_date - latest_news_date).days,
        "news_missing": False,
    }


def build_similar_case_features(*, similar_rows: list[dict], row_date: date) -> dict:
    matching_rows = [row for row in similar_rows if row["query_date"] == row_date]
    if not matching_rows:
        return empty_similar_case_features()

    best_row = sorted(
        matching_rows,
        key=lambda row: (
            safe_int(row.get("sample_size")) or 0,
            quality_rank(row.get("evidence_quality")),
        ),
        reverse=True,
    )[0]
    return {
        "similar_case_sample_size": safe_int(best_row.get("sample_size")) or 0,
        "similar_case_win_rate_5d": safe_float(best_row.get("win_rate_5d")),
        "similar_case_win_rate_10d": safe_float(best_row.get("win_rate_10d")),
        "similar_case_win_rate_20d": safe_float(best_row.get("win_rate_20d")),
        "similar_case_average_return_20d": safe_float(
            best_row.get("average_forward_return_20d")
        ),
        "similar_case_max_loss_20d": safe_float(best_row.get("max_loss_20d")),
        "similar_case_evidence_quality": best_row.get("evidence_quality") or "none",
    }


def empty_similar_case_features() -> dict:
    return {
        "similar_case_sample_size": 0,
        "similar_case_win_rate_5d": None,
        "similar_case_win_rate_10d": None,
        "similar_case_win_rate_20d": None,
        "similar_case_average_return_20d": None,
        "similar_case_max_loss_20d": None,
        "similar_case_evidence_quality": "none",
    }


def build_labels(
    *,
    technical_row: dict,
    price_rows: list[dict],
    price_index: int,
) -> dict | None:
    current_close = safe_float(price_rows[price_index].get("close"))
    if current_close is None or current_close == 0:
        return None

    forward_returns = {
        horizon: forward_return(price_rows, price_index, horizon)
        for horizon in [5, 10, 20]
    }
    if any(value is None for value in forward_returns.values()):
        return None

    max_drop_20d = future_max_drop(price_rows, price_index, 20)
    if max_drop_20d is None:
        return None

    labels = {
        "forward_return_5d": forward_returns[5],
        "forward_return_10d": forward_returns[10],
        "forward_return_20d": forward_returns[20],
        "up_5d": forward_returns[5] > 0,
        "up_10d": forward_returns[10] > 0,
        "up_20d": forward_returns[20] > 0,
        "non_upside_5d": forward_returns[5] <= 0,
        "non_upside_10d": forward_returns[10] <= 0,
        "non_upside_20d": forward_returns[20] <= 0,
        "large_drop_20d": max_drop_20d <= -0.08,
        "max_drop_20d": max_drop_20d,
        "expected_return_range_5d": None,
        "expected_return_range_10d": None,
        "expected_return_range_20d": None,
        "historical_average_return_5d": None,
        "historical_average_return_10d": None,
        "historical_average_return_20d": None,
        "breakout_success_20d": signal_success(
            triggered=bool(technical_row.get("is_breakout")),
            forward_return_20d=forward_returns[20],
        ),
        "pullback_success_20d": signal_success(
            triggered=bool(technical_row.get("is_pullback")),
            forward_return_20d=forward_returns[20],
        ),
        "volume_surge_success_20d": signal_success(
            triggered=bool(technical_row.get("is_volume_surge")),
            forward_return_20d=forward_returns[20],
        ),
    }
    return labels


def build_metadata(
    *,
    rows: list[dict],
    universe: str,
    feature_version: str,
    label_version: str,
    generated_at: str,
    excluded_reasons: Counter,
) -> dict:
    split_counts = Counter(row["split"] for row in rows)
    dates = [parse_date(row["date"]) for row in rows]
    return {
        "generated_at": generated_at,
        "data_start_date": min(dates).isoformat() if dates else None,
        "data_end_date": max(dates).isoformat() if dates else None,
        "universe": universe,
        "feature_version": feature_version,
        "label_version": label_version,
        "row_count": len(rows),
        "train_count": split_counts.get("train", 0),
        "validation_count": split_counts.get("validation", 0),
        "test_count": split_counts.get("test", 0),
        "excluded_row_reason_summary": dict(sorted(excluded_reasons.items())),
        "source_tables": [
            "daily_prices",
            "technical_features",
            "market_regimes",
            "news_events",
            "similar_case_results",
        ],
    }


def write_dataset_outputs(
    *,
    rows: list[dict],
    metadata: dict,
    csv_path: str | Path,
    metadata_path: str | Path,
) -> None:
    csv_path = Path(csv_path)
    metadata_path = Path(metadata_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = BASE_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_price_rows(rows: list[dict]) -> list[dict]:
    normalized = normalize_rows_by_date(rows)
    return [
        row
        for row in normalized
        if safe_float(row.get("close")) is not None
        and safe_float(row.get("volume", 0)) is not None
    ]


def normalize_rows_by_date(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        row_date = parse_optional_date(row.get("date"))
        if row_date is None:
            continue
        normalized.append({**row, "date": row_date})
    return sorted(normalized, key=lambda row: row["date"])


def normalize_news_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        published_date = parse_optional_date(row.get("published_at"))
        normalized.append({**row, "published_date": published_date})
    return sorted(
        normalized,
        key=lambda row: row["published_date"] or date.min,
    )


def normalize_similar_case_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        query_date = parse_optional_date(row.get("query_date"))
        if query_date is None:
            continue
        normalized.append({**row, "query_date": query_date})
    return sorted(normalized, key=lambda row: row["query_date"])


def classify_split(row_date: date) -> str | None:
    for split, (start_date, end_date) in SPLIT_RANGES.items():
        if row_date >= start_date and (end_date is None or row_date <= end_date):
            return split
    return None


def trailing_return(rows: list[dict], current_index: int, days: int) -> float | None:
    if current_index < days:
        return None

    current_close = safe_float(rows[current_index].get("close"))
    previous_close = safe_float(rows[current_index - days].get("close"))
    return ratio_delta(current_close, previous_close)


def forward_return(rows: list[dict], current_index: int, days: int) -> float | None:
    future_index = current_index + days
    if future_index >= len(rows):
        return None

    current_close = safe_float(rows[current_index].get("close"))
    future_close = safe_float(rows[future_index].get("close"))
    return ratio_delta(future_close, current_close)


def trailing_volatility(rows: list[dict], current_index: int, days: int) -> float | None:
    if current_index < days:
        return None

    returns = []
    start = current_index - days + 1
    for index in range(start, current_index + 1):
        previous_close = safe_float(rows[index - 1].get("close"))
        current_close = safe_float(rows[index].get("close"))
        value = ratio_delta(current_close, previous_close)
        if value is None:
            return None
        returns.append(value)

    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def trailing_volume_ratio(rows: list[dict], current_index: int, days: int) -> float | None:
    if current_index < days - 1:
        return None

    volumes = [
        safe_float(rows[index].get("volume"))
        for index in range(current_index - days + 1, current_index + 1)
    ]
    if any(volume is None for volume in volumes):
        return None

    average_volume = sum(volumes) / len(volumes)
    current_volume = safe_float(rows[current_index].get("volume"))
    if average_volume == 0 or current_volume is None:
        return None

    return current_volume / average_volume


def future_max_drop(rows: list[dict], current_index: int, days: int) -> float | None:
    if current_index + days >= len(rows):
        return None

    current_close = safe_float(rows[current_index].get("close"))
    future_closes = [
        safe_float(rows[index].get("close"))
        for index in range(current_index + 1, current_index + days + 1)
    ]
    if current_close is None or current_close == 0 or any(
        value is None for value in future_closes
    ):
        return None

    return min(future_closes) / current_close - 1


def signal_success(*, triggered: bool, forward_return_20d: float) -> bool | None:
    if not triggered:
        return None
    return forward_return_20d > 0


def ratio_delta(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator - 1


def count_matching(rows: list[dict], field: str, expected_value: str) -> int:
    return sum(1 for row in rows if row.get(field) == expected_value)


def score_news_sentiment(sentiment: str | None) -> int:
    if sentiment == "positive":
        return 1
    if sentiment == "negative":
        return -1
    return 0


def quality_rank(value: str | None) -> int:
    return {
        "high": 5,
        "medium": 4,
        "low_to_medium": 3,
        "low": 2,
        "none": 1,
    }.get(value or "none", 0)


def safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def safe_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_optional_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return parse_date(value)


def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return date.fromisoformat(text[:10])
