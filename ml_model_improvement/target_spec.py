from __future__ import annotations

from datetime import UTC, datetime


TARGET_METRIC_SPECS = {
    "up_5d": {
        "target_type": "classification",
        "horizon_trading_days": 5,
        "financial_meaning": "5 個交易日後收盤價是否高於訊號日收盤價。",
        "product_role": "短線方向參考，只能輔助判斷，不直接改變下單建議。",
        "primary_metrics": ["roc_auc", "brier_score", "calibration_error"],
        "secondary_metrics": ["accuracy", "precision", "recall"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "test_roc_auc": 0.53,
            "test_accuracy": 0.51,
            "max_mean_absolute_calibration_error": 0.10,
        },
        "risk_note": "5 日方向容易受短線雜訊影響，若 calibration 不佳，Research Report 必須降低信任。",
    },
    "up_10d": {
        "target_type": "classification",
        "horizon_trading_days": 10,
        "financial_meaning": "10 個交易日後收盤價是否高於訊號日收盤價。",
        "product_role": "短中線方向參考，用來觀察訊號是否延續。",
        "primary_metrics": ["roc_auc", "brier_score", "calibration_error"],
        "secondary_metrics": ["accuracy", "precision", "recall"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "test_roc_auc": 0.53,
            "test_accuracy": 0.51,
            "max_mean_absolute_calibration_error": 0.10,
        },
        "risk_note": "10 日方向應比 5 日更穩，但仍不能被解讀為明確漲幅預測。",
    },
    "up_20d": {
        "target_type": "classification",
        "horizon_trading_days": 20,
        "financial_meaning": "20 個交易日後收盤價是否高於訊號日收盤價。",
        "product_role": "主要 swing horizon 方向參考，也是目前 ML Health 的核心弱點之一。",
        "primary_metrics": ["roc_auc", "brier_score", "calibration_error"],
        "secondary_metrics": ["accuracy", "precision", "recall"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "test_roc_auc": 0.53,
            "test_accuracy": 0.51,
            "max_mean_absolute_calibration_error": 0.10,
        },
        "risk_note": "20 日方向如果低於門檻，ML Reference 必須顯示 reduced_trust。",
    },
    "large_drop_20d": {
        "target_type": "classification",
        "horizon_trading_days": 20,
        "financial_meaning": "未來 20 個交易日內是否曾從訊號日收盤價下跌 8% 以上。",
        "product_role": "風險控管核心訊號，優先級高於單純上漲機率。",
        "primary_metrics": ["large_drop_hit_rate", "brier_score", "downside_underestimation_rate"],
        "secondary_metrics": ["accuracy", "precision", "recall", "roc_auc"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "large_drop_hit_rate": 0.60,
            "max_downside_underestimation_rate": 0.20,
            "max_mean_absolute_calibration_error": 0.10,
        },
        "risk_note": "寧可保守，也不能系統性低估中途大跌風險。",
    },
    "forward_return_5d": {
        "target_type": "regression",
        "horizon_trading_days": 5,
        "financial_meaning": "5 個交易日後的收盤報酬率。",
        "product_role": "報酬模型實驗參考，低於歷史區間參考的優先級。",
        "primary_metrics": ["mae", "rmse", "directional_accuracy"],
        "secondary_metrics": ["downside_underestimation_rate"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "directional_accuracy": 0.52,
            "max_downside_underestimation_rate": 0.25,
        },
        "risk_note": "短期報酬率雜訊高，不能用單點預測當作價格目標。",
    },
    "forward_return_10d": {
        "target_type": "regression",
        "horizon_trading_days": 10,
        "financial_meaning": "10 個交易日後的收盤報酬率。",
        "product_role": "報酬區間參考，用來輔助歷史相似情境。",
        "primary_metrics": ["mae", "rmse", "directional_accuracy"],
        "secondary_metrics": ["downside_underestimation_rate"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "directional_accuracy": 0.52,
            "max_downside_underestimation_rate": 0.25,
        },
        "risk_note": "必須以區間呈現，不應只顯示單點報酬預測。",
    },
    "forward_return_20d": {
        "target_type": "regression",
        "horizon_trading_days": 20,
        "financial_meaning": "20 個交易日後的收盤報酬率。",
        "product_role": "swing horizon 報酬區間參考。",
        "primary_metrics": ["mae", "rmse", "directional_accuracy"],
        "secondary_metrics": ["downside_underestimation_rate"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "directional_accuracy": 0.52,
            "max_downside_underestimation_rate": 0.25,
        },
        "risk_note": "20 日報酬預測若品質低，應優先顯示歷史分位數區間。",
    },
    "max_drop_20d": {
        "target_type": "regression",
        "horizon_trading_days": 20,
        "financial_meaning": "未來 20 個交易日內，相對訊號日收盤價的最大中途跌幅。",
        "product_role": "出場觀察與風險控管核心參考。",
        "primary_metrics": ["mae", "downside_underestimation_rate"],
        "secondary_metrics": ["rmse"],
        "minimum_sample_size": 500,
        "promotion_floor": {
            "max_downside_underestimation_rate": 0.20,
        },
        "risk_note": "這個 target 應偏保守，低估風險比高估風險更糟。",
    },
}


def build_target_metric_spec_report(
    *,
    generated_at: datetime | None = None,
    benchmark_sources: list[str] | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    return {
        "report_version": "step15_target_metric_spec_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "benchmark_sources": benchmark_sources
        or ["microsoft/qlib", "AI4Finance-Foundation/FinRL"],
        "principles": [
            "Keep data, features, models, monitoring, and product display separated.",
            "Do not promote a candidate model without baseline comparison.",
            "Treat calibration and downside risk as first-class model quality metrics.",
            "Use ML Reference as research support, not as an automatic trade instruction.",
        ],
        "targets": TARGET_METRIC_SPECS,
    }


def build_target_metric_spec_summary_markdown(report: dict) -> str:
    lines = [
        "# Step 15 Target / Metric Spec",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Report version: `{report['report_version']}`",
        f"- Benchmark sources: {', '.join(report['benchmark_sources'])}",
        "",
        "## Principles",
        "",
    ]
    lines.extend(f"- {principle}" for principle in report["principles"])
    lines.extend(
        [
            "",
            "## Targets",
            "",
            "| Target | Type | Horizon | Product Role | Primary Metrics | Promotion Floor |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for target, spec in report["targets"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    target,
                    spec["target_type"],
                    str(spec["horizon_trading_days"]),
                    spec["product_role"],
                    ", ".join(spec["primary_metrics"]),
                    format_thresholds(spec["promotion_floor"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Risk Notes", ""])
    lines.extend(
        f"- `{target}`: {spec['risk_note']}"
        for target, spec in report["targets"].items()
    )
    return "\n".join(lines) + "\n"


def format_thresholds(thresholds: dict) -> str:
    return ", ".join(f"{key}={value}" for key, value in thresholds.items())
