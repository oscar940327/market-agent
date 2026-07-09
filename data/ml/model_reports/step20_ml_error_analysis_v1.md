# Step 20 ML Error Analysis

- Generated at: `2026-07-09T09:07:03+00:00`
- Universe: `QQQ100`
- Model version: `all_models`
- Window days: `90`
- Computed outcomes: `1000`
- Findings: `10`

## Horizon Summary

| Horizon | Samples | Up Accuracy | Actual Up Rate | Avg Probability | False Positive | False Negative | Probability Error | Downside Underestimation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5d | 334 | 55.4% | 50.6% | 48.2% | 6.0% | 38.6% | 49.5% | n/a |
| 10d | 332 | 59.0% | 42.8% | 46.5% | 1.8% | 39.2% | 49.4% | n/a |
| 20d | 334 | 45.8% | 52.7% | 46.2% | 3.9% | 50.3% | 50.7% | 56.0% |

## Worst Groups

### ticker

| Value | Samples | Worst Error Rate | 20d Downside Underestimation |
| --- | ---: | ---: | ---: |
| ARM | 12 | 100.0% | 100.0% |
| AXON | 12 | 100.0% | 100.0% |
| MAR | 12 | 100.0% | 75.0% |
| ALAB | 12 | 100.0% | 50.0% |
| ALNY | 12 | 100.0% | 50.0% |

### market_regime

| Value | Samples | Worst Error Rate | 20d Downside Underestimation |
| --- | ---: | ---: | ---: |
| bull | 1000 | 54.2% | 56.0% |

### technical_state

| Value | Samples | Worst Error Rate | 20d Downside Underestimation |
| --- | ---: | ---: | ---: |
| breakout | 96 | 72.7% | 57.6% |
| neutral | 47 | 66.7% | 40.0% |
| pullback | 376 | 63.2% | 45.6% |
| bullish | 204 | 57.4% | 60.3% |
| volume_surge | 48 | 50.0% | 75.0% |

### news_state

| Value | Samples | Worst Error Rate | 20d Downside Underestimation |
| --- | ---: | ---: | ---: |
| negative | 24 | 100.0% | 12.5% |
| risk_event | 15 | 80.0% | 20.0% |
| neutral | 168 | 55.4% | 60.7% |
| no_recent_news | 772 | 53.1% | 57.0% |
| positive | 21 | 42.9% | 57.1% |

### risk_state

| Value | Samples | Worst Error Rate | 20d Downside Underestimation |
| --- | ---: | ---: | ---: |
| elevated | 15 | 80.0% | 20.0% |
| medium | 43 | 64.3% | 28.6% |
| high | 942 | 53.3% | 57.8% |

## Findings

- warning / up_5d: 5-day probability error is above threshold. (value=49.5%)
- warning / up_10d: 10-day probability error is above threshold. (value=49.4%)
- warning / up_20d: 20-day up accuracy is below threshold. (value=45.8%)
- warning / up_20d: 20-day probability error is above threshold. (value=50.7%)
- critical / max_drop_20d: 20-day downside underestimation is above threshold. (value=56.0%)
- warning / ticker: ticker=ARM has high classification error. (value=100.0%)
- warning / market_regime: market_regime=bull has high classification error. (value=54.2%)
- warning / technical_state: technical_state=breakout has high classification error. (value=72.7%)
- warning / news_state: news_state=negative has high classification error. (value=100.0%)
- warning / risk_state: risk_state=elevated has high classification error. (value=80.0%)

## Next Actions

- Build a downside risk overlay before trusting 20-day max-drop outputs.
- Add calibrated probability outputs or conservative probability wording.
- Review feature importance and candidate models for weak horizon targets.
- Prioritize groups with high error rates in the next feature / candidate model pass.
