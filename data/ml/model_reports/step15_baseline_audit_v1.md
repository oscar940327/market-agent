# Step 15 Baseline Audit

- Generated at: `2026-07-05T20:55:06+00:00`
- Baseline model version: `baseline_v1`
- Return model version: `return_baseline_v1`
- Findings: `12` total, `5` critical, `7` warning

## Classification Targets

| Target | Status | Best Model | Test Accuracy | Test ROC AUC | Issues |
| --- | --- | --- | ---: | ---: | --- |
| up_5d | warning | logistic_regression | 0.506 | 0.524 | test ROC AUC 0.524 is below floor 0.530; test accuracy 0.506 is below floor 0.510 |
| up_10d | warning | random_forest | 0.500 | 0.521 | test ROC AUC 0.521 is below floor 0.530; test accuracy 0.500 is below floor 0.510 |
| up_20d | warning | logistic_regression | 0.495 | 0.528 | test ROC AUC 0.528 is below floor 0.530; test accuracy 0.495 is below floor 0.510 |
| large_drop_20d | warning | random_forest | 0.531 | 0.641 | large-drop hit rate is missing |

## Regression Targets

| Target | Status | Best Model | Test MAE | Directional Accuracy | Downside Underestimation | Issues |
| --- | --- | --- | ---: | ---: | ---: | --- |
| forward_return_5d | warning | random_forest_regressor | 0.037 | 0.534 | 0.996 | downside underestimation rate 0.996 is above ceiling 0.250 |
| forward_return_10d | warning | random_forest_regressor | 0.054 | 0.540 | 0.978 | downside underestimation rate 0.978 is above ceiling 0.250 |
| forward_return_20d | warning | random_forest_regressor | 0.079 | 0.551 | 0.980 | downside underestimation rate 0.980 is above ceiling 0.250 |
| max_drop_20d | warning | random_forest_regressor | 0.045 | n/a | 0.422 | downside underestimation rate 0.422 is above ceiling 0.200 |

## Findings

- warning / up_5d: test ROC AUC 0.524 is below floor 0.530
- warning / up_5d: test accuracy 0.506 is below floor 0.510
- warning / up_10d: test ROC AUC 0.521 is below floor 0.530
- warning / up_10d: test accuracy 0.500 is below floor 0.510
- warning / up_20d: test ROC AUC 0.528 is below floor 0.530
- warning / up_20d: test accuracy 0.495 is below floor 0.510
- critical / large_drop_20d: large-drop hit rate is missing
- critical / forward_return_5d: downside underestimation rate 0.996 is above ceiling 0.250
- critical / forward_return_10d: downside underestimation rate 0.978 is above ceiling 0.250
- critical / forward_return_20d: downside underestimation rate 0.980 is above ceiling 0.250
- critical / max_drop_20d: downside underestimation rate 0.422 is above ceiling 0.200
- warning / health: ML health status is unknown.

## Next Actions

- Improve classification features and candidate models before promotion.
- Prioritize downside risk modeling and conservative max-drop estimates.
