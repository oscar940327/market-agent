from datetime import UTC, date, datetime, timedelta


PRICE_WARNING_TRADING_DAYS = 1
PRICE_STALE_TRADING_DAYS = 2
NEWS_STALE_DAYS = 30
ML_WARNING_DAYS = 7
ML_STALE_DAYS = 14
PIPELINE_WARNING_HOURS = 24
PIPELINE_STALE_HOURS = 48


def build_freshness_report(
    *,
    today: date,
    daily_prices_latest_date: date | None,
    technical_features_latest_date: date | None,
    market_regimes_latest_date: date | None,
    news_latest_at: datetime | date | None = None,
    ml_training_generated_at: datetime | date | None = None,
    pipeline_last_run_at: datetime | date | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    today = today or now.date()
    daily_prices = classify_trading_day_freshness(
        today=today,
        latest_date=daily_prices_latest_date,
        label="daily_prices",
    )
    technical_features = classify_dependency_freshness(
        latest_date=technical_features_latest_date,
        dependency_latest_date=daily_prices_latest_date,
        label="technical_features",
        dependency_label="daily_prices",
    )
    market_regimes = classify_dependency_freshness(
        latest_date=market_regimes_latest_date,
        dependency_latest_date=daily_prices_latest_date,
        label="market_regimes",
        dependency_label="daily_prices",
    )
    news_events = classify_news_freshness(
        now=now,
        latest_at=news_latest_at,
    )
    ml_training_data = classify_ml_training_freshness(
        now=now,
        generated_at=ml_training_generated_at,
    )
    pipeline_last_run = classify_pipeline_run_freshness(
        now=now,
        last_run_at=pipeline_last_run_at,
    )
    sections = {
        "daily_prices": daily_prices,
        "technical_features": technical_features,
        "market_regimes": market_regimes,
        "news_events": news_events,
        "ml_training_data": ml_training_data,
        "pipeline_last_run": pipeline_last_run,
    }

    return {
        **sections,
        "overall": classify_overall([section["status"] for section in sections.values()]),
        "warnings": build_warning_messages(sections),
    }


def classify_trading_day_freshness(
    *,
    today: date,
    latest_date: date | None,
    label: str,
) -> dict:
    if latest_date is None:
        return {
            "status": "missing",
            "reason": "no_latest_date",
            "message": f"{label} 找不到最新日期。",
        }

    lag = count_business_days_between(latest_date, today)
    payload = {
        "latest_date": latest_date.isoformat(),
        "business_day_lag": lag,
    }

    if lag >= PRICE_STALE_TRADING_DAYS:
        return {
            **payload,
            "status": "stale",
            "reason": "latest_date_too_old",
            "message": f"{label} 已落後 {lag} 個交易日。",
        }

    if lag >= PRICE_WARNING_TRADING_DAYS:
        return {
            **payload,
            "status": "warning",
            "reason": "latest_date_one_trading_day_behind",
            "message": f"{label} 落後 1 個交易日，請留意資料是否已更新。",
        }

    return {
        **payload,
        "status": "fresh",
        "reason": "latest_trading_day_available",
        "message": f"{label} 已是最新交易日資料。",
    }


def classify_dependency_freshness(
    *,
    latest_date: date | None,
    dependency_latest_date: date | None,
    label: str,
    dependency_label: str,
) -> dict:
    if latest_date is None:
        return {
            "status": "missing",
            "reason": "no_latest_date",
            "message": f"{label} 找不到最新日期。",
        }

    if dependency_latest_date is None:
        return {
            "status": "missing",
            "reason": "dependency_missing",
            "latest_date": latest_date.isoformat(),
            "message": f"{label} 找不到依賴的 {dependency_label} 日期。",
        }

    lag = count_business_days_between(latest_date, dependency_latest_date)
    payload = {
        "latest_date": latest_date.isoformat(),
        "dependency_latest_date": dependency_latest_date.isoformat(),
        "business_day_lag": lag,
    }

    if lag >= PRICE_STALE_TRADING_DAYS:
        return {
            **payload,
            "status": "stale",
            "reason": "behind_dependency",
            "message": f"{label} 已落後 {dependency_label} {lag} 個交易日。",
        }

    if lag >= PRICE_WARNING_TRADING_DAYS:
        return {
            **payload,
            "status": "warning",
            "reason": "one_trading_day_behind_dependency",
            "message": f"{label} 落後 {dependency_label} 1 個交易日。",
        }

    return {
        **payload,
        "status": "fresh",
        "reason": "matches_dependency",
        "message": f"{label} 已和 {dependency_label} 同步。",
    }


def classify_news_freshness(*, now: datetime, latest_at: datetime | date | None) -> dict:
    if latest_at is None:
        return {
            "status": "stale",
            "reason": "no_news_in_30_days",
            "message": "新聞資料過舊（最近 30 天內沒有新聞）。",
        }

    latest_datetime = coerce_datetime(latest_at)
    age_days = (now - latest_datetime).days
    payload = {
        "latest_at": latest_datetime.isoformat(),
        "age_days": age_days,
    }

    if age_days >= NEWS_STALE_DAYS:
        return {
            **payload,
            "status": "stale",
            "reason": "no_news_in_30_days",
            "message": "新聞資料過舊（最近 30 天內沒有新聞）。",
        }

    return {
        **payload,
        "status": "fresh",
        "reason": "news_within_30_days",
        "message": "新聞資料在 30 天內有更新。",
    }


def classify_ml_training_freshness(
    *,
    now: datetime,
    generated_at: datetime | date | None,
) -> dict:
    if generated_at is None:
        return {
            "status": "missing",
            "reason": "missing_ml_training_metadata",
            "message": "找不到 ML training dataset metadata。",
        }

    generated_datetime = coerce_datetime(generated_at)
    age_days = (now - generated_datetime).days
    payload = {
        "generated_at": generated_datetime.isoformat(),
        "age_days": age_days,
    }

    if age_days > ML_STALE_DAYS:
        return {
            **payload,
            "status": "stale",
            "reason": "ml_training_data_too_old",
            "message": f"ML training dataset 已超過 {ML_STALE_DAYS} 天未更新。",
        }

    if age_days > ML_WARNING_DAYS:
        return {
            **payload,
            "status": "warning",
            "reason": "ml_training_data_getting_old",
            "message": "ML training dataset 已超過 7 天未更新。",
        }

    return {
        **payload,
        "status": "fresh",
        "reason": "ml_training_data_recent",
        "message": "ML training dataset 在 7 天內更新。",
    }


def classify_pipeline_run_freshness(
    *,
    now: datetime,
    last_run_at: datetime | date | None,
) -> dict:
    if last_run_at is None:
        return {
            "status": "missing",
            "reason": "missing_pipeline_run_log",
            "message": "找不到最近一次 pipeline run log。",
        }

    last_run_datetime = coerce_datetime(last_run_at)
    age_hours = (now - last_run_datetime).total_seconds() / 3600
    payload = {
        "last_run_at": last_run_datetime.isoformat(),
        "age_hours": round(age_hours, 2),
    }

    if age_hours > PIPELINE_STALE_HOURS:
        return {
            **payload,
            "status": "stale",
            "reason": "pipeline_run_too_old",
            "message": "每日 pipeline 已超過 48 小時沒有成功執行紀錄。",
        }

    if age_hours > PIPELINE_WARNING_HOURS:
        return {
            **payload,
            "status": "warning",
            "reason": "pipeline_run_getting_old",
            "message": "每日 pipeline 已超過 24 小時沒有成功執行紀錄。",
        }

    return {
        **payload,
        "status": "fresh",
        "reason": "pipeline_run_recent",
        "message": "每日 pipeline 最近 24 小時內有執行紀錄。",
    }


def classify_overall(statuses: list[str]) -> str:
    if "missing" in statuses:
        return "missing"

    if "stale" in statuses:
        return "stale"

    if "warning" in statuses:
        return "warning"

    return "fresh"


def build_warning_messages(sections: dict[str, dict]) -> list[str]:
    warnings = []
    for name, section in sections.items():
        if section.get("status") in {"warning", "stale", "missing"}:
            warnings.append(
                {
                    "source": name,
                    "status": section.get("status"),
                    "reason": section.get("reason"),
                    "message": section.get("message"),
                }
            )
    return warnings


def count_business_days_between(start: date, end: date) -> int:
    if start >= end:
        return 0

    current = start
    count = 0
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count


def coerce_datetime(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
