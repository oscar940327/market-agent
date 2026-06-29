from datetime import date


FRESHNESS_MAX_AGE_DAYS = 3


def build_freshness_report(
    *,
    today: date,
    daily_prices_latest_date: date | None,
    technical_features_latest_date: date | None,
    market_regimes_latest_date: date | None,
) -> dict:
    daily_prices = classify_freshness(
        today=today,
        latest_date=daily_prices_latest_date,
    )
    technical_features = classify_dependency_freshness(
        latest_date=technical_features_latest_date,
        dependency_latest_date=daily_prices_latest_date,
    )
    market_regimes = classify_dependency_freshness(
        latest_date=market_regimes_latest_date,
        dependency_latest_date=daily_prices_latest_date,
    )

    return {
        "daily_prices": daily_prices,
        "technical_features": technical_features,
        "market_regimes": market_regimes,
        "overall": classify_overall(
            [
                daily_prices["status"],
                technical_features["status"],
                market_regimes["status"],
            ]
        ),
    }


def classify_freshness(*, today: date, latest_date: date | None) -> dict:
    if latest_date is None:
        return {"status": "missing", "reason": "no_latest_date"}

    age_days = (today - latest_date).days
    if age_days > FRESHNESS_MAX_AGE_DAYS:
        return {
            "status": "stale",
            "reason": "latest_date_too_old",
            "age_days": age_days,
        }

    return {"status": "fresh", "reason": "within_allowed_age", "age_days": age_days}


def classify_dependency_freshness(
    *,
    latest_date: date | None,
    dependency_latest_date: date | None,
) -> dict:
    if latest_date is None:
        return {"status": "missing", "reason": "no_latest_date"}

    if dependency_latest_date is None:
        return {"status": "missing", "reason": "dependency_missing"}

    if latest_date < dependency_latest_date:
        return {
            "status": "stale",
            "reason": "behind_dependency",
            "latest_date": latest_date.isoformat(),
            "dependency_latest_date": dependency_latest_date.isoformat(),
        }

    return {
        "status": "fresh",
        "reason": "matches_dependency",
        "latest_date": latest_date.isoformat(),
        "dependency_latest_date": dependency_latest_date.isoformat(),
    }


def classify_overall(statuses: list[str]) -> str:
    if "missing" in statuses:
        return "missing"

    if "stale" in statuses:
        return "stale"

    return "fresh"
