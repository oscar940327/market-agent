# Step 28 ML Model Quality Upgrade

- Generated at: `2026-07-16T15:39:07+00:00`
- Evaluation: `expanding_walk_forward_with_final_holdout`
- Dataset: `333232` rows / `106` tickers
- Promotion status: `do_not_promote`
- ML Reference policy: `reduced_trust`

## Target Results

| Target | Type | Best Candidate | Quality | Promotion | Failed Checks |
| --- | --- | --- | --- | --- | --- |
| up_5d | classification | logistic_regression_calibrated_sigmoid | low | reject | holdout_roc_auc, brier_improvement_vs_naive, accuracy_delta_vs_naive |
| up_10d | classification | logistic_regression_calibrated_sigmoid | low | reject | holdout_roc_auc, brier_improvement_vs_naive, walk_forward_stability, market_regime_stability, accuracy_delta_vs_naive |
| up_20d | classification | random_forest_calibrated_sigmoid | low | reject | holdout_roc_auc, brier_improvement_vs_naive, accuracy_delta_vs_naive |
| large_drop_20d | classification | random_forest_calibrated_sigmoid | medium | pass | none |
| forward_return_5d | regression | random_forest | low_to_medium | reject | mae_improvement_vs_naive |
| forward_return_10d | regression | xgboost | low | reject | mae_improvement_vs_naive, walk_forward_stability, market_regime_stability |
| forward_return_20d | regression | random_forest | low | reject | mae_improvement_vs_naive, walk_forward_stability, market_regime_stability |
| max_drop_20d | regression | random_forest | low_to_medium | reject | mae_improvement_vs_naive, downside_underestimation_rate |

## Promotion Decision

- Passed targets: large_drop_20d
- Blocked targets: up_5d, up_10d, up_20d, max_drop_20d
- Action: keep current production models and reduced_trust policy
- Candidate models never replace production automatically.
