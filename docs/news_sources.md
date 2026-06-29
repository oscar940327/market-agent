# Step 6.8 News Sources

This is the first source plan for `news_events`.

## Current Decision

- Use news only in Step 6.8. Social sources stay in Step 6.9.
- Prefer free, reasonably timely, and higher-trust sources.
- Start with rule-based normalization and classification.
- All LLM usage should prefer OpenRouter so report generation and news extraction
  share one provider/key path.
- Low-cost OpenRouter models can be used later as an optional extractor after
  extraction cache is in place.
- News should inform the News Analysis section and supporting summary, not directly
  override the final conclusion from a single article.

## First Provider Candidates

| Source | Cost | Timeliness | Trust | First Role | Notes |
| --- | --- | --- | --- | --- | --- |
| Google News RSS | Free | Good | Mixed aggregator | Broad ticker news discovery | Needs dedup and source quality checks. |
| Yahoo Finance / yfinance news | Free | Good | Medium | Ticker-specific news | API shape can change because it is not an official paid feed. |
| Company IR / press release RSS | Free | Good | High | Future high-quality company events | Provider differs by company. |
| SEC filings | Free | Good | High | Future filings / risk events | May deserve a dedicated filings flow later. |
| Earnings transcripts | Often limited | Delayed | High | Future earnings context | Free access can be inconsistent. |

## First Implementation Scope

- Implement Google News RSS.
- Implement Yahoo/yfinance news when available.
- Normalize rows into Supabase `news_events`.
- Generate `duplicate_group_id`.
- Generate `ticker_mapping_confidence`.
- Classify `source_quality`.
- Classify sentiment / topic / importance with rule-based logic by default.
- Optional OpenRouter extraction should only run for new or unclassified rows after
  the cache step is implemented.

## LLM Plan

- Default: `rule_based`.
- Optional extractor: OpenRouter mini model such as `openai/gpt-5.4-mini` or
  `openai/gpt-4.1-mini`.
- Escalation model: stronger OpenRouter model such as `openai/gpt-5.5`, only for
  risk-event news, high-importance unclear news, or high-quality unclear news.
- Low ticker relevance should not escalate; it should be treated as low-weight
  evidence instead of spending more tokens.
- Do not make LLM extraction the default until duplicate/news classification cache
  prevents repeated token usage.
