# Step 20 ML Improvement Summary

- Generated at: `2026-07-09T09:25:29+00:00`
- Final status: `do_not_promote`
- ML Reference policy: `reduced_trust`
- Computed outcomes: `1000`

## Key Findings

- 20-day up accuracy is 45.8%, and downside underestimation is 56.0%.
- Calibration action report has 4 finding(s), so calibrated probabilities should remain reduced-trust.
- Candidate v2 is not ready for promotion for: up_5d, up_10d, up_20d, large_drop_20d.

## Decisions

- `promote_candidate_model`: `no`
- `ml_reference_policy`: `reduced_trust`
- `replace_raw_probability_with_calibrated_probability`: `no`
- `use_downside_risk_overlay`: `yes`
- `keep_news_and_similar_cases_out_of_core_model`: `yes`

## Final Recommendation

- Keep baseline_v1 visible as reduced-trust ML Reference. Use downside overlay as a conservative risk layer, but do not replace raw probabilities with calibrated values yet.

## Next Actions

- Monitor whether downside overlay reduces max-drop underestimation in future outcomes.
- Keep calibrated probabilities in model reports first; do not show them as primary report values yet.
- Do not promote candidate v2; continue feature engineering and outcome accumulation.
- Re-run Step 20 after more computed outcomes mature.
