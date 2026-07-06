# Step 15 Model Comparison / Promotion Review

- Generated at: `2026-07-06T10:27:14+00:00`
- Final status: `do_not_promote`
- ML Reference policy: `reduced_trust`
- Message: Do not promote Step 15 candidate models. Keep ML Reference visible but reduced-trust.

## Target Comparison

| Target | Baseline | Candidate | Accuracy Delta | ROC AUC Delta | Decision |
| --- | --- | --- | ---: | ---: | --- |
| up_5d | logistic_regression | logistic_regression_calibrated_sigmoid | 0.037 | 0.001 | reject |
| up_10d | random_forest | xgboost_calibrated_sigmoid | 0.002 | 0.004 | reject |
| up_20d | logistic_regression | logistic_regression | 0.003 | 0.001 | reject |
| large_drop_20d | random_forest | random_forest_calibrated_sigmoid | 0.216 | -0.003 | reject |

## Risk Review

- Status: `not_ready`
- ML Reference trust: `reduced_trust`
- critical / forward_return_5d: downside underestimation rate 0.996 is above ceiling 0.250
- critical / forward_return_10d: downside underestimation rate 0.978 is above ceiling 0.250
- critical / forward_return_20d: downside underestimation rate 0.980 is above ceiling 0.250
- critical / max_drop_20d: downside underestimation rate 0.422 is above ceiling 0.200
- critical / large_drop_20d: large_drop_20d candidate is not ready for promotion.
- warning / news_features: news features should remain low-trust for ML training until coverage improves.
- warning / similar_cases: similar-case features should not be core model inputs yet.

## Promotion Policy

- Recommendation: `reject`
- Do not promote a model unless static metrics, monitoring outcomes, calibration, and risk review pass.
- Do not use news or similar-case features as core ML inputs until coverage improves.
- Do not promote a candidate that worsens downside underestimation.
- Manual approval is required before replacing production ML Reference.

## Documentation Notes

- Step 15 introduced a model improvement framework based on target specs, baseline audit, diagnostics, candidate experiments, calibration, and promotion policy.
- Current candidate models should not replace production ML Reference.
- Research Report should keep ML Reference visible but reduced-trust until downside risk and calibration improve.
- Downside risk remains the main blocker; max-drop and large-drop monitoring should be improved before promotion.
- Calibrated variants improved some static metrics, but calibration alone was not enough for promotion.
- README / model policy should clearly say the current ML model is research-only and not production-grade investment advice.
