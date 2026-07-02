from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import pandas as pd


DEFAULT_FEATURES = [
    "rsi_14",
    "macd_histogram",
    "return_5d",
    "return_10d",
    "return_20d",
    "volatility_20d",
    "volume_ratio_20d",
    "price_vs_ma20",
    "price_vs_ma50",
    "price_vs_ma200",
    "news_sentiment_score_30d",
    "news_count_30d",
]
DEFAULT_THRESHOLDS = {
    "feature_std_multiplier": 2.0,
    "news_missing_ratio": 0.30,
    "news_count_drop_ratio": 0.50,
}


def build_drift_report_from_csv(
    csv_path: str | Path,
    *,
    recent_days: int = 30,
    baseline_days: int = 365,
    freshness_report: dict | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    dataset = pd.read_csv(csv_path)
    return build_drift_report(
        dataset,
        recent_days=recent_days,
        baseline_days=baseline_days,
        freshness_report=freshness_report,
        generated_at=generated_at,
        thresholds=thresholds,
    )


def build_drift_report(
    dataset: pd.DataFrame,
    *,
    recent_days: int = 30,
    baseline_days: int = 365,
    freshness_report: dict | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    generated = generated_at or datetime.now(UTC)
    normalized = normalize_dataset(dataset)
    windows = split_windows(normalized, recent_days=recent_days, baseline_days=baseline_days)
    feature_drift = build_feature_drift(
        recent=windows["recent"],
        baseline=windows["baseline"],
        thresholds=thresholds,
    )
    market_regime_drift = build_market_regime_drift(windows["recent"])
    news_coverage_drift = build_news_coverage_drift(
        recent=windows["recent"],
        baseline=windows["baseline"],
        thresholds=thresholds,
    )
    data_freshness_drift = build_data_freshness_drift(freshness_report)
    warnings = (
        feature_drift["warnings"]
        + market_regime_drift["warnings"]
        + news_coverage_drift["warnings"]
        + data_freshness_drift["warnings"]
    )
    return {
        "report_version": "ml_drift_report_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "recent_days": recent_days,
        "baseline_days": baseline_days,
        "dataset_rows": len(normalized),
        "recent_rows": len(windows["recent"]),
        "baseline_rows": len(windows["baseline"]),
        "date_range": build_date_range(normalized),
        "feature_drift": feature_drift,
        "market_regime_drift": market_regime_drift,
        "news_coverage_drift": news_coverage_drift,
        "data_freshness_drift": data_freshness_drift,
        "warnings": warnings,
        "alert": {
            "should_alert": bool(warnings),
            "severity": "warning" if warnings else "info",
            "reason": "drift_warning" if warnings else "drift_ok",
        },
    }


def normalize_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    normalized = dataset.copy()
    if normalized.empty:
        return normalized
    normalized["date"] = pd.to_datetime(normalized["date"])
    return normalized.sort_values("date")


def split_windows(dataset: pd.DataFrame, *, recent_days: int, baseline_days: int) -> dict[str, pd.DataFrame]:
    if dataset.empty:
        return {"recent": dataset.copy(), "baseline": dataset.copy()}
    latest_date = dataset["date"].max()
    recent_start = latest_date - pd.Timedelta(days=recent_days)
    baseline_start = latest_date - pd.Timedelta(days=baseline_days)
    recent = dataset[dataset["date"] > recent_start]
    baseline = dataset[(dataset["date"] > baseline_start) & (dataset["date"] <= recent_start)]
    if baseline.empty:
        baseline = dataset[dataset["date"] <= recent_start]
    return {"recent": recent, "baseline": baseline}


def build_feature_drift(*, recent: pd.DataFrame, baseline: pd.DataFrame, thresholds: dict) -> dict:
    features = []
    warnings = []
    for feature in DEFAULT_FEATURES:
        if feature not in recent.columns or feature not in baseline.columns:
            continue
        recent_values = numeric_values(recent[feature])
        baseline_values = numeric_values(baseline[feature])
        if not recent_values or not baseline_values:
            features.append(
                {
                    "feature": feature,
                    "status": "insufficient_data",
                    "recent_count": len(recent_values),
                    "baseline_count": len(baseline_values),
                }
            )
            continue
        baseline_std = pstdev(baseline_values)
        recent_mean = mean(recent_values)
        baseline_mean = mean(baseline_values)
        mean_diff = recent_mean - baseline_mean
        if baseline_std:
            z_score = abs(mean_diff) / baseline_std
        else:
            z_score = 999999.0 if abs(mean_diff) > 1e-12 else 0.0
        status = "warning" if z_score > thresholds["feature_std_multiplier"] else "ok"
        record = {
            "feature": feature,
            "status": status,
            "recent_count": len(recent_values),
            "baseline_count": len(baseline_values),
            "recent_mean": round(recent_mean, 6),
            "baseline_mean": round(baseline_mean, 6),
            "baseline_std": round(baseline_std, 6),
            "mean_diff": round(mean_diff, 6),
            "z_score": round(z_score, 6),
        }
        features.append(record)
        if status == "warning":
            warnings.append(
                {
                    "source": "feature_drift",
                    "status": "warning",
                    "metric": feature,
                    "value": record["z_score"],
                    "threshold": thresholds["feature_std_multiplier"],
                    "message": f"{feature} recent mean moved more than threshold vs baseline.",
                }
            )
    return {"features": features, "warnings": warnings}


def build_market_regime_drift(recent: pd.DataFrame) -> dict:
    warnings = []
    regime_counts = value_counts(recent, "market_regime")
    qqq_above_rate = mean_bool(recent.get("qqq_above_ma200"))
    regime_changed_rate = mean_bool(recent.get("regime_changed"))
    latest_row = recent.sort_values("date").iloc[-1].to_dict() if not recent.empty else {}
    latest_regime_changed = bool(latest_row.get("regime_changed")) if latest_row else False
    latest_qqq_above = latest_row.get("qqq_above_ma200") if latest_row else None

    if latest_regime_changed:
        warnings.append(
            {
                "source": "market_regime_drift",
                "status": "warning",
                "metric": "regime_changed",
                "value": True,
                "threshold": False,
                "message": "Latest market regime row is marked as changed.",
            }
        )
    if latest_qqq_above is False:
        warnings.append(
            {
                "source": "market_regime_drift",
                "status": "warning",
                "metric": "qqq_above_ma200",
                "value": False,
                "threshold": True,
                "message": "QQQ is below MA200 in the latest market snapshot.",
            }
        )

    return {
        "latest_market_regime": latest_row.get("market_regime"),
        "latest_qqq_above_ma200": latest_qqq_above,
        "latest_regime_changed": latest_regime_changed,
        "recent_regime_counts": regime_counts,
        "recent_qqq_above_ma200_rate": qqq_above_rate,
        "recent_regime_changed_rate": regime_changed_rate,
        "warnings": warnings,
    }


def build_news_coverage_drift(*, recent: pd.DataFrame, baseline: pd.DataFrame, thresholds: dict) -> dict:
    warnings = []
    recent_missing_ratio = mean_bool(recent.get("news_missing")) or 0.0
    baseline_news_count = numeric_values(baseline.get("news_count_30d", []))
    recent_news_count = numeric_values(recent.get("news_count_30d", []))
    baseline_avg_news = mean(baseline_news_count) if baseline_news_count else None
    recent_avg_news = mean(recent_news_count) if recent_news_count else None
    news_count_ratio = (
        recent_avg_news / baseline_avg_news
        if baseline_avg_news and recent_avg_news is not None
        else None
    )

    if recent_missing_ratio > thresholds["news_missing_ratio"]:
        warnings.append(
            {
                "source": "news_coverage_drift",
                "status": "warning",
                "metric": "news_missing_ratio",
                "value": round(recent_missing_ratio, 6),
                "threshold": thresholds["news_missing_ratio"],
                "message": "Recent news_missing ratio is above threshold.",
            }
        )
    if news_count_ratio is not None and news_count_ratio < thresholds["news_count_drop_ratio"]:
        warnings.append(
            {
                "source": "news_coverage_drift",
                "status": "warning",
                "metric": "news_count_ratio",
                "value": round(news_count_ratio, 6),
                "threshold": thresholds["news_count_drop_ratio"],
                "message": "Recent average news count dropped below baseline threshold.",
            }
        )

    return {
        "recent_news_missing_ratio": round(recent_missing_ratio, 6),
        "recent_avg_news_count_30d": round(recent_avg_news, 6) if recent_avg_news is not None else None,
        "baseline_avg_news_count_30d": round(baseline_avg_news, 6) if baseline_avg_news is not None else None,
        "news_count_ratio": round(news_count_ratio, 6) if news_count_ratio is not None else None,
        "warnings": warnings,
    }


def build_data_freshness_drift(freshness_report: dict | None) -> dict:
    if not freshness_report:
        return {"overall": "unknown", "warnings": []}
    warnings = []
    for source, value in freshness_report.items():
        if not isinstance(value, dict):
            continue
        status = value.get("status")
        if status in {"stale", "missing"}:
            warnings.append(
                {
                    "source": "data_freshness",
                    "status": "warning",
                    "metric": source,
                    "value": status,
                    "threshold": "fresh_or_warning",
                    "message": f"{source} freshness is {status}.",
                }
            )
    return {
        "overall": freshness_report.get("overall", "unknown"),
        "report": freshness_report,
        "warnings": warnings,
    }


def build_drift_summary_markdown(report: dict) -> str:
    lines = [
        "# ML Drift Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Recent window: `{report['recent_days']}` days",
        f"- Baseline window: `{report['baseline_days']}` days",
        f"- Dataset rows: `{report['dataset_rows']}`",
        f"- Recent rows: `{report['recent_rows']}`",
        f"- Baseline rows: `{report['baseline_rows']}`",
        "",
        "## Feature Drift",
        "",
        "| Feature | Status | Recent Mean | Baseline Mean | Baseline Std | Z Score |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for feature in report["feature_drift"]["features"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    feature.get("feature", ""),
                    feature.get("status", ""),
                    format_number(feature.get("recent_mean")),
                    format_number(feature.get("baseline_mean")),
                    format_number(feature.get("baseline_std")),
                    format_number(feature.get("z_score")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Market Regime",
            "",
            f"- Latest regime: `{report['market_regime_drift'].get('latest_market_regime')}`",
            f"- Latest QQQ above MA200: `{report['market_regime_drift'].get('latest_qqq_above_ma200')}`",
            f"- Latest regime changed: `{report['market_regime_drift'].get('latest_regime_changed')}`",
            "",
            "## News Coverage",
            "",
            f"- Recent news missing ratio: `{format_percent(report['news_coverage_drift'].get('recent_news_missing_ratio'))}`",
            f"- News count ratio: `{format_number(report['news_coverage_drift'].get('news_count_ratio'))}`",
            "",
            "## Data Freshness",
            "",
            f"- Overall: `{report['data_freshness_drift'].get('overall')}`",
            "",
            "## Warnings",
            "",
        ]
    )
    if report["warnings"]:
        lines.extend(f"- {warning['message']} ({warning['source']} / {warning['metric']})" for warning in report["warnings"])
    else:
        lines.append("- No warnings.")
    return "\n".join(lines) + "\n"


def numeric_values(values) -> list[float]:
    if values is None:
        return []
    series = pd.Series(values)
    return [float(value) for value in pd.to_numeric(series, errors="coerce").dropna().tolist()]


def value_counts(dataset: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in dataset.columns or dataset.empty:
        return {}
    return {str(key): int(value) for key, value in dataset[column].value_counts(dropna=True).items()}


def mean_bool(values) -> float | None:
    if values is None:
        return None
    series = pd.Series(values).dropna()
    if series.empty:
        return None
    mapped = series.map(lambda value: bool(value))
    return round(float(mapped.mean()), 6)


def build_date_range(dataset: pd.DataFrame) -> dict[str, str | None]:
    if dataset.empty:
        return {"start": None, "end": None}
    return {
        "start": dataset["date"].min().date().isoformat(),
        "end": dataset["date"].max().date().isoformat(),
    }


def format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def format_percent(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)
