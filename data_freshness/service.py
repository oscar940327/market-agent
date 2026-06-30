import json
from datetime import UTC, date, datetime
from pathlib import Path

from data_store.supabase_store import fetch_latest_date
from market_regime import build_freshness_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ML_METADATA_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"
DEFAULT_PIPELINE_LOG_DIR = PROJECT_ROOT / "data" / "pipeline_runs"


def build_current_data_freshness(
    *,
    ticker: str | None = None,
    benchmark: str = "QQQ",
    provider: str = "yfinance",
    feature_version: str = "v1",
    rule_version: str = "v1",
    today: date | None = None,
    now: datetime | None = None,
    ml_metadata_path: str | Path = DEFAULT_ML_METADATA_PATH,
    pipeline_log_dir: str | Path = DEFAULT_PIPELINE_LOG_DIR,
) -> dict:
    now = now or datetime.now(UTC)
    today = today or now.date()
    price_ticker = (ticker or benchmark).upper()

    daily_prices_latest = safe_fetch_latest_date(
        table="daily_prices",
        filters={"ticker": f"eq.{price_ticker}", "provider": f"eq.{provider}"},
    )
    technical_features_latest = safe_fetch_latest_date(
        table="technical_features",
        filters={
            "ticker": f"eq.{price_ticker}",
            "price_provider": f"eq.{provider}",
            "feature_version": f"eq.{feature_version}",
        },
    )
    market_regimes_latest = safe_fetch_latest_date(
        table="market_regimes",
        filters={"benchmark": f"eq.{benchmark.upper()}", "rule_version": f"eq.{rule_version}"},
    )
    news_latest = safe_fetch_latest_date(
        table="news_events",
        date_column="published_at",
        filters={"ticker": f"eq.{price_ticker}"},
    )

    report = build_freshness_report(
        today=today,
        now=now,
        daily_prices_latest_date=parse_date(daily_prices_latest),
        technical_features_latest_date=parse_date(technical_features_latest),
        market_regimes_latest_date=parse_date(market_regimes_latest),
        news_latest_at=parse_datetime(news_latest),
        ml_training_generated_at=read_ml_metadata_generated_at(ml_metadata_path),
        pipeline_last_run_at=read_latest_pipeline_run_at(pipeline_log_dir),
    )
    report["scope"] = {
        "ticker": price_ticker,
        "benchmark": benchmark.upper(),
        "provider": provider,
        "feature_version": feature_version,
        "rule_version": rule_version,
    }
    return report


def safe_fetch_latest_date(
    *,
    table: str,
    date_column: str = "date",
    filters: dict[str, str] | None = None,
) -> str | None:
    try:
        return fetch_latest_date(
            table=table,
            date_column=date_column,
            filters=filters,
        )
    except Exception:
        return None


def read_ml_metadata_generated_at(path: str | Path) -> datetime | None:
    metadata_path = Path(path)
    if not metadata_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    return parse_datetime(metadata.get("generated_at"))


def read_latest_pipeline_run_at(log_dir: str | Path) -> datetime | None:
    directory = Path(log_dir)
    if not directory.exists():
        return None

    logs = sorted(directory.glob("daily_pipeline_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for log_path in logs:
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        finished_at = parse_datetime(payload.get("finished_at"))
        if finished_at:
            return finished_at

    return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)
