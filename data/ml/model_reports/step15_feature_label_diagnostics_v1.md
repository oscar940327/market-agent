# Step 15 Feature / Label Diagnostics

- Generated at: `2026-07-05T20:55:07+00:00`
- Rows: `327387`
- Tickers: `101`
- Date range: `2012-02-09` to `2026-05-28`
- Warnings: `8`

## Split Counts

- test: 84845
- train: 194492
- validation: 48050

## Core Labels

| Label | Count | Positive Rate / Mean | Test Positive Rate / Mean |
| --- | ---: | ---: | ---: |
| up_5d | 327387 | 0.550 | 0.544 |
| up_10d | 327387 | 0.566 | 0.556 |
| up_20d | 327387 | 0.587 | 0.571 |
| large_drop_20d | 327387 | 0.212 | 0.227 |
| forward_return_5d | 327387 | 0.005 | 0.007 |
| forward_return_10d | 327387 | 0.010 | 0.013 |
| forward_return_20d | 327387 | 0.020 | 0.025 |
| max_drop_20d | 327387 | -0.048 | -0.050 |

## Feature Groups

| Group | Columns | Avg Missing | Coverage Detail |
| --- | ---: | ---: | --- |
| technical | 8 | 0.000 | n/a |
| market | 5 | 0.000 | n/a |
| news | 8 | 0.125 | news_missing=1.0, avg_news=0.0 |
| similar_cases | 7 | 0.714 | empty_cases=1.0, avg_sample=0.0 |

## Warnings

- days_since_last_news missing rate is high. (days_since_last_news=1.0)
- similar_case_win_rate_5d missing rate is high. (similar_case_win_rate_5d=1.0)
- similar_case_win_rate_10d missing rate is high. (similar_case_win_rate_10d=1.0)
- similar_case_win_rate_20d missing rate is high. (similar_case_win_rate_20d=1.0)
- similar_case_average_return_20d missing rate is high. (similar_case_average_return_20d=1.0)
- similar_case_max_loss_20d missing rate is high. (similar_case_max_loss_20d=1.0)
- News coverage is sparse for the training dataset. (news_missing_rate=1.0)
- Similar-case evidence is mostly empty. (empty_similar_case_rate=1.0)

## Next Actions

- Treat news features as low-trust until coverage improves.
- Do not rely on similar-case features as core model inputs yet.
- Review high-missing features before training candidate models.
