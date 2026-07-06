# Step 15 Target / Metric Spec

- Generated at: `2026-07-05T20:55:06+00:00`
- Report version: `step15_target_metric_spec_v1`
- Benchmark sources: microsoft/qlib, AI4Finance-Foundation/FinRL

## Principles

- Keep data, features, models, monitoring, and product display separated.
- Do not promote a candidate model without baseline comparison.
- Treat calibration and downside risk as first-class model quality metrics.
- Use ML Reference as research support, not as an automatic trade instruction.

## Targets

| Target | Type | Horizon | Product Role | Primary Metrics | Promotion Floor |
| --- | --- | ---: | --- | --- | --- |
| up_5d | classification | 5 | 短線方向參考，只能輔助判斷，不直接改變下單建議。 | roc_auc, brier_score, calibration_error | test_roc_auc=0.53, test_accuracy=0.51, max_mean_absolute_calibration_error=0.1 |
| up_10d | classification | 10 | 短中線方向參考，用來觀察訊號是否延續。 | roc_auc, brier_score, calibration_error | test_roc_auc=0.53, test_accuracy=0.51, max_mean_absolute_calibration_error=0.1 |
| up_20d | classification | 20 | 主要 swing horizon 方向參考，也是目前 ML Health 的核心弱點之一。 | roc_auc, brier_score, calibration_error | test_roc_auc=0.53, test_accuracy=0.51, max_mean_absolute_calibration_error=0.1 |
| large_drop_20d | classification | 20 | 風險控管核心訊號，優先級高於單純上漲機率。 | large_drop_hit_rate, brier_score, downside_underestimation_rate | large_drop_hit_rate=0.6, max_downside_underestimation_rate=0.2, max_mean_absolute_calibration_error=0.1 |
| forward_return_5d | regression | 5 | 報酬模型實驗參考，低於歷史區間參考的優先級。 | mae, rmse, directional_accuracy | directional_accuracy=0.52, max_downside_underestimation_rate=0.25 |
| forward_return_10d | regression | 10 | 報酬區間參考，用來輔助歷史相似情境。 | mae, rmse, directional_accuracy | directional_accuracy=0.52, max_downside_underestimation_rate=0.25 |
| forward_return_20d | regression | 20 | swing horizon 報酬區間參考。 | mae, rmse, directional_accuracy | directional_accuracy=0.52, max_downside_underestimation_rate=0.25 |
| max_drop_20d | regression | 20 | 出場觀察與風險控管核心參考。 | mae, downside_underestimation_rate | max_downside_underestimation_rate=0.2 |

## Risk Notes

- `up_5d`: 5 日方向容易受短線雜訊影響，若 calibration 不佳，Research Report 必須降低信任。
- `up_10d`: 10 日方向應比 5 日更穩，但仍不能被解讀為明確漲幅預測。
- `up_20d`: 20 日方向如果低於門檻，ML Reference 必須顯示 reduced_trust。
- `large_drop_20d`: 寧可保守，也不能系統性低估中途大跌風險。
- `forward_return_5d`: 短期報酬率雜訊高，不能用單點預測當作價格目標。
- `forward_return_10d`: 必須以區間呈現，不應只顯示單點報酬預測。
- `forward_return_20d`: 20 日報酬預測若品質低，應優先顯示歷史分位數區間。
- `max_drop_20d`: 這個 target 應偏保守，低估風險比高估風險更糟。
