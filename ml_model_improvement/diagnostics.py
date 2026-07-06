from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ml_dataset import FEATURE_COLUMNS, LABEL_COLUMNS


CORE_LABELS = [
    "up_5d",
    "up_10d",
    "up_20d",
    "large_drop_20d",
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "max_drop_20d",
]
CORE_FEATURE_GROUPS = {
    "technical": [
        "price_vs_ma20",
        "price_vs_ma50",
        "price_vs_ma200",
        "rsi_14",
        "macd",
        "macd_histogram",
        "volatility_20d",
        "volume_ratio_20d",
    ],
    "market": [
        "market_regime",
        "qqq_above_ma200",
        "qqq_return_20d",
        "qqq_return_60d",
        "regime_changed",
    ],
    "news": [
        "news_count_30d",
        "news_sentiment_score_30d",
        "high_importance_news_count_30d",
        "risk_event_count_30d",
        "earnings_guidance_count_30d",
        "product_demand_count_30d",
        "days_since_last_news",
        "news_missing",
    ],
    "similar_cases": [
        "similar_case_sample_size",
        "similar_case_win_rate_5d",
        "similar_case_win_rate_10d",
        "similar_case_win_rate_20d",
        "similar_case_average_return_20d",
        "similar_case_max_loss_20d",
        "similar_case_evidence_quality",
    ],
}
DEFAULT_DIAGNOSTIC_THRESHOLDS = {
    "max_core_feature_missing_rate": 0.20,
    "max_news_missing_rate": 0.70,
    "max_similar_case_empty_rate": 0.90,
    "min_label_positive_rate": 0.10,
    "max_label_positive_rate": 0.90,
}


def build_feature_label_diagnostics_report(
    dataset: pd.DataFrame,
    *,
    metadata: dict | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
) -> dict:
    thresholds = {**DEFAULT_DIAGNOSTIC_THRESHOLDS, **(thresholds or {})}
    generated = generated_at or datetime.now(UTC)
    split_counts = build_split_counts(dataset)
    label_summary = build_label_summary(dataset)
    feature_missing = build_feature_missing_summary(dataset)
    feature_groups = build_feature_group_summary(dataset)
    market_regime = build_market_regime_summary(dataset)
    warnings = build_diagnostic_warnings(
        label_summary=label_summary,
        feature_missing=feature_missing,
        feature_groups=feature_groups,
        thresholds=thresholds,
    )
    return {
        "report_version": "step15_feature_label_diagnostics_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "thresholds": thresholds,
        "metadata": metadata or {},
        "row_count": int(len(dataset)),
        "ticker_count": int(dataset["ticker"].nunique()) if "ticker" in dataset else None,
        "date_range": build_date_range(dataset),
        "split_counts": split_counts,
        "label_summary": label_summary,
        "feature_missing_summary": feature_missing,
        "feature_group_summary": feature_groups,
        "market_regime_summary": market_regime,
        "warnings": warnings,
        "next_actions": build_diagnostic_next_actions(warnings),
    }


def build_split_counts(dataset: pd.DataFrame) -> dict:
    if "split" not in dataset:
        return {}
    return {
        str(split): int(count)
        for split, count in dataset["split"].value_counts(dropna=False).sort_index().items()
    }


def build_label_summary(dataset: pd.DataFrame) -> dict:
    summary = {}
    for label in CORE_LABELS:
        if label not in dataset:
            summary[label] = {"status": "missing"}
            continue
        split_summary = {}
        for split, frame in split_dataset(dataset).items():
            values = frame[label].dropna()
            if values.empty:
                split_summary[split] = {"count": 0}
                continue
            split_summary[split] = summarize_label_values(values)
        summary[label] = {
            "status": "available",
            "overall": summarize_label_values(dataset[label].dropna()),
            "by_split": split_summary,
        }
    return summary


def summarize_label_values(values: pd.Series) -> dict:
    if values.empty:
        return {"count": 0}
    if is_boolean_like(values):
        numeric = values.map(to_bool).astype(int)
        return {
            "count": int(len(numeric)),
            "positive_rate": round(float(numeric.mean()), 6),
        }
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"count": int(len(values))}
    return {
        "count": int(len(numeric)),
        "mean": round(float(numeric.mean()), 6),
        "median": round(float(numeric.median()), 6),
        "p25": round(float(numeric.quantile(0.25)), 6),
        "p75": round(float(numeric.quantile(0.75)), 6),
    }


def build_feature_missing_summary(dataset: pd.DataFrame) -> dict:
    summary = {}
    for feature in FEATURE_COLUMNS:
        if feature not in dataset:
            summary[feature] = {"status": "missing_column", "missing_rate": 1.0}
            continue
        missing_rate = float(dataset[feature].isna().mean())
        summary[feature] = {
            "status": "available",
            "missing_rate": round(missing_rate, 6),
        }
    return summary


def build_feature_group_summary(dataset: pd.DataFrame) -> dict:
    summary = {}
    for group, columns in CORE_FEATURE_GROUPS.items():
        existing = [column for column in columns if column in dataset]
        if not existing:
            summary[group] = {"status": "missing", "missing_rate": 1.0}
            continue
        missing_rates = [float(dataset[column].isna().mean()) for column in existing]
        payload = {
            "status": "available",
            "column_count": len(existing),
            "average_missing_rate": round(sum(missing_rates) / len(missing_rates), 6),
        }
        if group == "news" and "news_missing" in dataset:
            payload["news_missing_rate"] = round(float(dataset["news_missing"].map(to_bool).mean()), 6)
            payload["average_news_count_30d"] = round(float(pd.to_numeric(dataset.get("news_count_30d"), errors="coerce").fillna(0).mean()), 6)
        if group == "similar_cases" and "similar_case_sample_size" in dataset:
            sample_size = pd.to_numeric(dataset["similar_case_sample_size"], errors="coerce").fillna(0)
            payload["empty_similar_case_rate"] = round(float((sample_size <= 0).mean()), 6)
            payload["average_sample_size"] = round(float(sample_size.mean()), 6)
        summary[group] = payload
    return summary


def build_market_regime_summary(dataset: pd.DataFrame) -> dict:
    if "market_regime" not in dataset:
        return {"status": "missing"}
    counts = dataset["market_regime"].fillna("unknown").astype(str).value_counts()
    total = len(dataset)
    return {
        "status": "available",
        "distribution": {
            regime: {
                "count": int(count),
                "rate": round(float(count / total), 6) if total else None,
            }
            for regime, count in counts.items()
        },
    }


def build_diagnostic_warnings(
    *,
    label_summary: dict,
    feature_missing: dict,
    feature_groups: dict,
    thresholds: dict,
) -> list[dict]:
    warnings = []
    for feature, summary in feature_missing.items():
        missing_rate = summary.get("missing_rate")
        if missing_rate is not None and missing_rate > thresholds["max_core_feature_missing_rate"]:
            warnings.append(
                {
                    "source": "feature_missing",
                    "status": "warning",
                    "metric": feature,
                    "value": missing_rate,
                    "threshold": thresholds["max_core_feature_missing_rate"],
                    "message": f"{feature} missing rate is high.",
                }
            )
    news_missing_rate = feature_groups.get("news", {}).get("news_missing_rate")
    if news_missing_rate is not None and news_missing_rate > thresholds["max_news_missing_rate"]:
        warnings.append(
            {
                "source": "news_coverage",
                "status": "warning",
                "metric": "news_missing_rate",
                "value": news_missing_rate,
                "threshold": thresholds["max_news_missing_rate"],
                "message": "News coverage is sparse for the training dataset.",
            }
        )
    similar_empty = feature_groups.get("similar_cases", {}).get("empty_similar_case_rate")
    if similar_empty is not None and similar_empty > thresholds["max_similar_case_empty_rate"]:
        warnings.append(
            {
                "source": "similar_cases",
                "status": "warning",
                "metric": "empty_similar_case_rate",
                "value": similar_empty,
                "threshold": thresholds["max_similar_case_empty_rate"],
                "message": "Similar-case evidence is mostly empty.",
            }
        )
    for label, summary in label_summary.items():
        positive_rate = (summary.get("overall") or {}).get("positive_rate")
        if positive_rate is None:
            continue
        if positive_rate < thresholds["min_label_positive_rate"] or positive_rate > thresholds["max_label_positive_rate"]:
            warnings.append(
                {
                    "source": "label_balance",
                    "status": "warning",
                    "metric": label,
                    "value": positive_rate,
                    "message": f"{label} positive rate is imbalanced.",
                }
            )
    return warnings


def build_diagnostic_next_actions(warnings: list[dict]) -> list[str]:
    actions = []
    sources = {warning["source"] for warning in warnings}
    if "news_coverage" in sources:
        actions.append("Treat news features as low-trust until coverage improves.")
    if "similar_cases" in sources:
        actions.append("Do not rely on similar-case features as core model inputs yet.")
    if "feature_missing" in sources:
        actions.append("Review high-missing features before training candidate models.")
    if "label_balance" in sources:
        actions.append("Use class weighting or threshold tuning for imbalanced labels.")
    if not actions:
        actions.append("Feature and label diagnostics are usable for candidate model experiments.")
    return dedupe(actions)


def build_feature_label_diagnostics_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 15 Feature / Label Diagnostics",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Rows: `{report['row_count']}`",
        f"- Tickers: `{report.get('ticker_count')}`",
        f"- Date range: `{report['date_range'].get('start')}` to `{report['date_range'].get('end')}`",
        f"- Warnings: `{len(report['warnings'])}`",
        "",
        "## Split Counts",
        "",
    ]
    lines.extend(f"- {split}: {count}" for split, count in report["split_counts"].items())
    lines.extend(
        [
            "",
            "## Core Labels",
            "",
            "| Label | Count | Positive Rate / Mean | Test Positive Rate / Mean |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for label, summary in report["label_summary"].items():
        overall = summary.get("overall") or {}
        test = (summary.get("by_split") or {}).get("test") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    str(overall.get("count", 0)),
                    format_summary_value(overall),
                    format_summary_value(test),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Feature Groups",
            "",
            "| Group | Columns | Avg Missing | Coverage Detail |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for group, summary in report["feature_group_summary"].items():
        detail = []
        if "news_missing_rate" in summary:
            detail.append(f"news_missing={summary['news_missing_rate']}")
            detail.append(f"avg_news={summary['average_news_count_30d']}")
        if "empty_similar_case_rate" in summary:
            detail.append(f"empty_cases={summary['empty_similar_case_rate']}")
            detail.append(f"avg_sample={summary['average_sample_size']}")
        lines.append(
            "| "
            + " | ".join(
                [
                    group,
                    str(summary.get("column_count", 0)),
                    format_number(summary.get("average_missing_rate")),
                    ", ".join(detail) if detail else "n/a",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning['message']} ({warning['metric']}={warning['value']})" for warning in report["warnings"])
    else:
        lines.append("- No warnings.")

    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def split_dataset(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "split" not in dataset:
        return {"all": dataset}
    return {
        str(split): frame.copy()
        for split, frame in dataset.groupby("split", dropna=False)
    }


def build_date_range(dataset: pd.DataFrame) -> dict:
    if "date" not in dataset or dataset.empty:
        return {"start": None, "end": None}
    dates = pd.to_datetime(dataset["date"], errors="coerce").dropna()
    if dates.empty:
        return {"start": None, "end": None}
    return {
        "start": dates.min().date().isoformat(),
        "end": dates.max().date().isoformat(),
    }


def is_boolean_like(values: pd.Series) -> bool:
    unique = {str(value).strip().lower() for value in values.dropna().unique()}
    return bool(unique) and unique.issubset({"true", "false", "1", "0", "yes", "no"})


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def format_summary_value(summary: dict) -> str:
    if "positive_rate" in summary:
        return format_number(summary.get("positive_rate"))
    if "mean" in summary:
        return format_number(summary.get("mean"))
    return "n/a"


def format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
