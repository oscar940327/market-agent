# Step 15 Candidate Model Experiment

- Generated at: `2026-07-05T21:02:16+00:00`
- Feature policy: `technical_market_core_v1`
- Excluded groups: news, similar_cases

## Target Results

| Target | Status | Best Model | Test Accuracy | Test ROC AUC | Test Brier | Promotion Readiness |
| --- | --- | --- | ---: | ---: | ---: | --- |
| up_5d | success | logistic_regression_calibrated_sigmoid | 0.544 | 0.525 | 0.249 | not_ready |
| up_10d | success | xgboost_calibrated_sigmoid | 0.501 | 0.525 | 0.250 | not_ready |
| up_20d | success | logistic_regression | 0.499 | 0.529 | 0.252 | not_ready |
| large_drop_20d | success | random_forest_calibrated_sigmoid | 0.746 | 0.638 | 0.182 | not_ready |

## Recommendations

- Do not promote any candidate model without monitoring-outcome and calibration comparison.
- Keep news and similar-case features excluded from core candidate training until coverage improves.
- Continue feature engineering and calibration before considering promotion.
