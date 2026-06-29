import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import fetch_latest_date  # noqa: E402
from market_regime import build_freshness_report  # noqa: E402


def parse_optional_date(value: str | None):
    return date.fromisoformat(value) if value else None


def main() -> int:
    benchmark = "QQQ"
    provider = "yfinance"
    daily_prices_latest = fetch_latest_date(
        table="daily_prices",
        filters={"ticker": f"eq.{benchmark}", "provider": f"eq.{provider}"},
    )
    technical_features_latest = fetch_latest_date(
        table="technical_features",
        filters={
            "ticker": f"eq.{benchmark}",
            "price_provider": f"eq.{provider}",
            "feature_version": "eq.v1",
        },
    )
    market_regimes_latest = fetch_latest_date(
        table="market_regimes",
        filters={"benchmark": f"eq.{benchmark}", "rule_version": "eq.v1"},
    )
    report = build_freshness_report(
        today=date.today(),
        daily_prices_latest_date=parse_optional_date(daily_prices_latest),
        technical_features_latest_date=parse_optional_date(technical_features_latest),
        market_regimes_latest_date=parse_optional_date(market_regimes_latest),
    )

    print(f"daily_prices_latest={daily_prices_latest}")
    print(f"technical_features_latest={technical_features_latest}")
    print(f"market_regimes_latest={market_regimes_latest}")
    print(f"overall={report['overall']}")
    print(f"daily_prices={report['daily_prices']['status']}")
    print(f"technical_features={report['technical_features']['status']}")
    print(f"market_regimes={report['market_regimes']['status']}")

    return 0 if report["overall"] == "fresh" else 1


if __name__ == "__main__":
    raise SystemExit(main())
