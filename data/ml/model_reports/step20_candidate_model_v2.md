# Step 20 Candidate Model v2 Experiment

- Generated at: `2026-07-09T09:19:22+00:00`
- Feature policy: `technical_market_core_v1`
- Excluded groups: news, similar_cases

## Target Results

| Target | Status | Best Model | Test Accuracy | Test ROC AUC | Test Brier | Promotion Readiness |
| --- | --- | --- | ---: | ---: | ---: | --- |
| up_5d | success | logistic_regression | 0.508 | 0.525 | 0.250 | not_ready |
| up_10d | success | random_forest_calibrated_sigmoid | 0.505 | 0.525 | 0.249 | not_ready |
| up_20d | success | logistic_regression | 0.497 | 0.529 | 0.252 | not_ready |
| large_drop_20d | success | random_forest_calibrated_sigmoid | 0.742 | 0.652 | 0.183 | not_ready |

## Recommendations

- Do not promote any candidate model without monitoring-outcome and calibration comparison.
- Keep news and similar-case features excluded from core candidate training until coverage improves.
- Continue feature engineering and calibration before considering promotion.
- Step 20 candidate v2 must be reviewed with error analysis, calibration action, and downside overlay before promotion.
