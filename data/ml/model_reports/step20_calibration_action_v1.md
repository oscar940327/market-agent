# Step 20 Calibration Action Report

- Generated at: `2026-07-09T09:13:53+00:00`
- Universe: `QQQ100`
- Model version: `all_models`
- Window days: `90`
- Findings: `4`

## Target Actions

| Target | Samples | Usable Buckets | Mean Abs Error | Max Error | Recommendation |
| --- | ---: | ---: | ---: | ---: | --- |
| up_5d | 334 | 2 | 25.6% | 60.9% | calibration_table_usable_but_large_adjustments |
| up_10d | 332 | 1 | 10.4% | 15.9% | insufficient_bucket_coverage |
| up_20d | 334 | 2 | 11.5% | 13.2% | calibration_table_usable_but_large_adjustments |
| large_drop_20d | 334 | 4 | 23.1% | 36.1% | calibration_table_usable_but_large_adjustments |

## Bucket Adjustments

### up_5d

| Bucket | Samples | Avg Predicted | Actual Rate | Suggested | Adjustment | Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.4-0.5 | 273 | 47.5% | 46.9% | 46.9% | -0.6% | use_calibrated_probability |
| 0.5-0.6 | 60 | 51.5% | 66.7% | 66.7% | +15.2% | use_calibrated_probability_with_reduced_trust |

### up_10d

| Bucket | Samples | Avg Predicted | Actual Rate | Suggested | Adjustment | Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.4-0.5 | 312 | 46.3% | 41.3% | 41.3% | -5.0% | use_calibrated_probability |

### up_20d

| Bucket | Samples | Avg Predicted | Actual Rate | Suggested | Adjustment | Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.4-0.5 | 309 | 45.9% | 54.0% | 54.0% | +8.1% | use_calibrated_probability |
| 0.5-0.6 | 21 | 51.1% | 38.1% | 38.1% | -13.1% | use_calibrated_probability_with_reduced_trust |

### large_drop_20d

| Bucket | Samples | Avg Predicted | Actual Rate | Suggested | Adjustment | Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.4-0.5 | 22 | 45.9% | 18.2% | 18.2% | -27.7% | use_calibrated_probability_with_reduced_trust |
| 0.5-0.6 | 109 | 55.2% | 19.3% | 19.3% | -35.9% | use_calibrated_probability_with_reduced_trust |
| 0.6-0.7 | 151 | 64.6% | 51.0% | 51.0% | -13.6% | use_calibrated_probability_with_reduced_trust |
| 0.7-0.8 | 45 | 73.4% | 80.0% | 80.0% | +6.6% | use_calibrated_probability |

## Findings

- warning / up_5d: up_5d has 1 large calibration adjustment(s).
- warning / up_10d: up_10d has too few usable calibration buckets.
- warning / up_20d: up_20d has 1 large calibration adjustment(s).
- warning / large_drop_20d: large_drop_20d has 3 large calibration adjustment(s).

## Next Actions

- Show calibrated probabilities as reduced-trust until more outcomes accumulate.
- Keep raw probability wording conservative for sparse calibration buckets.
- Do not replace raw model probabilities until calibrated output is tested in reports.
