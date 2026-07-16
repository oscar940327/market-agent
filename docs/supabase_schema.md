# Supabase Schema Draft

這份文件是 Step 6.1 的 schema 草案。它只定義資料表、欄位、關聯與未來
migration 方向；目前不連 Supabase、不匯入真實資料。

正式連到 Supabase 的時間點是 **Step 6.2：Supabase 連線與 Migration**。

## Design Principles

- 第一版直接設計全部核心表，不只挑幾張表。
- 原始資料與衍生資料分開：`daily_prices` 存 OHLCV，`technical_features` 存技術指標。
- 價格資料允許多 provider，第一版唯一鍵使用 `ticker + date + provider`。
- QQQ100 / QQQ holdings universe 以 provider 為主，`data/themes.py` 只作為 theme classification / fallback。
- `market_regimes` 需要支援每日檢查，regime 轉換時要能留下紀錄。
- `similar_case_results` 可以快取查詢結果，但必須有 freshness / stale 規則。
- 新聞與社群在 Step 6.8 / 6.9 深入討論；Step 6.1 先保留核心 schema。
- 不記錄 API key、Supabase secrets 或任何敏感資料。

## Tables Overview

| Table | Purpose | First Used In |
| --- | --- | --- |
| `tickers` | 股票 universe 與 metadata | Step 6.3 |
| `daily_prices` | 每日 OHLCV 原始價格資料 | Step 6.4 |
| `technical_features` | 每日技術指標與訊號 | Step 6.5 |
| `market_regimes` | 每日市場環境與 regime 轉換紀錄 | Step 6.6 |
| `news_events` | 新聞事件與新聞特徵 | Step 6.8 |
| `social_events` | 社群事件與社群特徵 | Step 6.9 |
| `research_logs` | 使用者研究問題與當時系統輸出摘要 | Step 6.7 |
| `similar_case_results` | peer / market-wide 相似案例查詢結果 | Step 6.6 |
| `ml_dataset_metadata` | 跨 GitHub Actions、Render、本地共用的 ML dataset freshness metadata | Step 29 |

## Table: ml_dataset_metadata

這張表保存最新 training dataset 的版本、產生時間、資料截止日、row count 與 workflow run id。唯一鍵為 `dataset_name + universe + provider`，weekly workflow 以 upsert 更新；它不保存大型 CSV 本身。

Freshness service 優先讀取這張表，本地 metadata JSON 只作為 fallback。Schema 由 `supabase/migrations/014_create_ml_dataset_metadata.sql` 建立。

## Enum Drafts

這些 enum 可先用 text + check constraint，Step 6.2 migration 時再決定要不要建立
Postgres enum type。

### Common Status

- `fresh`
- `stale`
- `missing`
- `planned`

### Market Regime

- `bull`
- `bear`
- `sideways`
- `unknown`

### Evidence Quality

- `high`
- `medium`
- `low_to_medium`
- `low`
- `none`
- `not_used`
- `not_applicable`
- `skipped`
- `unknown`

### Event Sentiment

- `positive`
- `negative`
- `neutral`
- `unknown`

### Event Importance / Source Quality

- `high`
- `medium`
- `low`
- `unknown`

## Table: tickers

股票 universe 與 metadata。這張表回答：「目前系統支援哪些 ticker？它們來自哪個
provider？屬於哪些主題？」

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key, default `gen_random_uuid()` |
| `ticker` | text | yes | Uppercase ticker, e.g. `MU` |
| `name` | text | no | Company / fund name |
| `industry` | text | no | Provider 或後續分類資料 |
| `themes` | text[] | yes | Default `{}`；可由 `data/themes.py` 補充 |
| `market_cap_bucket` | text | no | `large`, `mid`, `small`, `unknown`; planned |
| `volatility_bucket` | text | no | `high`, `medium`, `low`, `unknown`; planned |
| `universe` | text | yes | First version: `QQQ100` or `QQQ_HOLDINGS` |
| `universe_provider` | text | yes | e.g. `provider_name`, not `data/themes.py` as source of truth |
| `is_active` | boolean | yes | Whether ticker is currently in active universe |
| `first_seen_at` | timestamptz | no | First time this ticker entered local universe |
| `last_seen_at` | timestamptz | no | Last time provider confirmed this ticker |
| `updated_at` | timestamptz | yes | Metadata update time |
| `created_at` | timestamptz | yes | Row creation time |

Keys and indexes:

- Primary key: `id`
- Unique: `ticker + universe`
- Index: `ticker`
- Index: `universe, is_active`
- Index: `themes` using GIN, if supported by migration

Relations:

- Referenced by `daily_prices.ticker`
- Referenced by `technical_features.ticker`
- Referenced by `news_events.ticker`
- Referenced by `social_events.ticker`
- Referenced by `research_logs.ticker`

## Table: daily_prices

每日 OHLCV 原始價格資料。這張表不存技術指標，避免原始資料與衍生資料混在一起。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `ticker` | text | yes | References `tickers.ticker` logically |
| `date` | date | yes | Trading date |
| `open` | numeric | yes | Daily open |
| `high` | numeric | yes | Daily high |
| `low` | numeric | yes | Daily low |
| `close` | numeric | yes | Daily close |
| `adj_close` | numeric | no | Adjusted close, if provider supports it |
| `volume` | numeric | yes | Daily volume |
| `provider` | text | yes | e.g. `yfinance`, `stooq`, future provider |
| `fetched_at` | timestamptz | yes | When data was fetched |
| `source_revision` | text | no | Provider batch/version marker; planned |
| `created_at` | timestamptz | yes | Row creation time |
| `updated_at` | timestamptz | yes | Row update time |

Keys and indexes:

- Primary key: `id`
- Unique: `ticker + date + provider`
- Index: `ticker, date`
- Index: `provider, fetched_at`

Rules:

- Multiple providers are allowed for the same `ticker + date`.
- Query layer must choose preferred provider explicitly.
- Missing trading days should remain missing; do not create fake price rows.
- Stocks with less than 15 years of history must be marked by data-window logic, not patched here.

## Table: technical_features

每日技術特徵與訊號。這張表由 `daily_prices` 計算而來，可重算。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `ticker` | text | yes | Ticker |
| `date` | date | yes | Feature date |
| `price_provider` | text | yes | Which price provider generated this feature |
| `close` | numeric | yes | Close used for feature calculation |
| `volume` | numeric | yes | Volume used for feature calculation |
| `ma20` | numeric | no | Moving average 20 |
| `ma50` | numeric | no | Moving average 50 |
| `rsi_14` | numeric | no | Use display label `RSI 14` in UI |
| `macd` | numeric | no | MACD value |
| `macd_signal` | numeric | no | MACD signal line |
| `macd_histogram` | numeric | no | MACD histogram |
| `short_term_trend` | text | no | `strong`, `neutral`, `weak`, `unknown` |
| `momentum_state` | text | no | Existing technical momentum state |
| `is_breakout` | boolean | yes | Default false |
| `is_volume_surge` | boolean | yes | Default false |
| `is_pullback` | boolean | yes | Default false |
| `feature_version` | text | yes | e.g. `v1`; needed when formulas change |
| `computed_at` | timestamptz | yes | Feature computation time |

Keys and indexes:

- Primary key: `id`
- Unique: `ticker + date + price_provider + feature_version`
- Index: `ticker, date`
- Index: `is_breakout, date`
- Index: `is_volume_surge, date`
- Index: `is_pullback, date`
- Index: `momentum_state, date`

Relations:

- Derived from `daily_prices`.
- Used by `similar_case_results` and future ML features.

## Table: market_regimes

每日市場環境與 regime 轉換紀錄。第一版用 QQQ 或 SPY 判斷 bull / bear / sideways。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `date` | date | yes | Regime date |
| `benchmark` | text | yes | `QQQ` or `SPY` |
| `regime` | text | yes | `bull`, `bear`, `sideways`, `unknown` |
| `close` | numeric | no | Benchmark close used |
| `ma200` | numeric | no | Benchmark MA200 |
| `three_month_return` | numeric | no | Used for trend direction |
| `regime_changed` | boolean | yes | True when regime differs from prior check |
| `previous_regime` | text | no | Prior regime |
| `rule_version` | text | yes | e.g. `v1` |
| `data_as_of` | date | yes | Latest data date used |
| `checked_at` | timestamptz | yes | Daily check timestamp |

Keys and indexes:

- Primary key: `id`
- Unique: `date + benchmark + rule_version`
- Index: `benchmark, date`
- Index: `regime, date`
- Index: `regime_changed, checked_at`

Rules:

- Daily check should recompute the latest benchmark regime.
- If regime changes, `regime_changed` is true and `previous_regime` is stored.
- If regime does not change, still store or update check metadata so freshness is visible.

## Table: news_events

新聞事件與新聞特徵。Step 6.1 先定義 schema，來源與授權在 Step 6.8 深入討論。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `ticker` | text | yes | Mapped ticker |
| `source` | text | yes | e.g. `Google News RSS`, `Yahoo Finance` |
| `source_type` | text | yes | `news`, `press_release`, `sec_filing`, `transcript` |
| `title` | text | yes | News title |
| `content_snippet` | text | no | Short excerpt / summary |
| `url` | text | no | Source URL |
| `published_at` | timestamptz | no | Publication time |
| `fetched_at` | timestamptz | yes | Fetch time |
| `sentiment` | text | yes | `positive`, `negative`, `neutral`, `unknown` |
| `topic` | text | yes | `earnings`, `guidance`, `industry_demand`, etc. |
| `importance` | text | yes | `high`, `medium`, `low`, `unknown` |
| `source_quality` | text | yes | `high`, `medium`, `low`, `unknown` |
| `duplicate_group_id` | text | no | Groups same event from multiple sources |
| `ticker_mapping_confidence` | text | no | `high`, `medium`, `low`, `unknown` |
| `extractor_mode` | text | no | `rule_based` or `llm`; Step 6.8I |
| `extractor_provider` | text | no | e.g. `openrouter`; Step 6.8I |
| `extractor_model` | text | no | e.g. `openai/gpt-5.4-mini`; Step 6.8I |
| `extracted_at` | timestamptz | no | When classification was produced |
| `extraction_status` | text | yes | `unclassified`, `success`, `fallback_rule_based`, `error`, `skipped_duplicate` |
| `llm_summary` | text | no | One-sentence LLM summary; do not replace source snippet |
| `ticker_relevance` | text | no | `high`, `medium`, `low`, `unknown` |
| `extraction_error` | text | no | Error message when extractor falls back or fails |
| `escalation_enabled` | boolean | yes | Whether escalation was enabled for this classification run |
| `escalated` | boolean | yes | True when escalation model result was applied |
| `escalation_model` | text | no | e.g. `openai/gpt-5.5` |
| `escalation_reason` | text | no | Why escalation was or was not used |
| `escalation_status` | text | yes | `not_applicable`, `not_needed`, `success`, `failed` |
| `escalation_error` | text | no | Error message when escalation fails |
| `created_at` | timestamptz | yes | Row creation time |

Keys and indexes:

- Primary key: `id`
- Unique candidate: `url`, if URL is available
- Index: `ticker, published_at`
- Index: `duplicate_group_id`
- Index: `topic, published_at`
- Index: `importance, published_at`
- Index: `extraction_status, fetched_at`
- Index: `extractor_mode, extracted_at`
- Index: `escalation_status, fetched_at`
- Index: `escalated, fetched_at`

Rules:

- Same event from multiple articles should share `duplicate_group_id`.
- Low quality source should not become high quality evidence by volume alone.
- Single news item should not directly change investment conclusion.
- Ingestion should deduplicate before expensive LLM classification.
- `scripts/classify_news_events.py` should classify only unclassified rows by default.
- Existing classification can be reused for rows with the same `duplicate_group_id`.
- Research Report should read stored classification/cache metadata, not call LLM during report generation.
- Escalation is optional and conservative: low ticker relevance should not escalate.
- Escalation should be cached so stronger-model calls are not repeated.

## Table: social_events

社群事件與社群特徵。Step 6.1 先定義 schema，來源、授權、spam / pump risk 在
Step 6.9 深入討論。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `ticker` | text | yes | Mapped ticker |
| `source` | text | yes | `Threads`, `Reddit`, `X`, `Stocktwits`, etc. |
| `source_type` | text | yes | `social` |
| `post_id` | text | no | Platform post ID |
| `author_id_hash` | text | no | Optional hashed ID; do not store sensitive data |
| `content_snippet` | text | no | Short text only |
| `url` | text | no | Source URL |
| `published_at` | timestamptz | no | Publication time |
| `fetched_at` | timestamptz | yes | Fetch time |
| `sentiment` | text | yes | `positive`, `negative`, `neutral`, `unknown` |
| `topic` | text | no | planned |
| `engagement_count` | integer | no | Likes/comments/reposts if available |
| `discussion_volume` | integer | no | Aggregated volume marker |
| `source_quality` | text | yes | `high`, `medium`, `low`, `unknown` |
| `spam_risk` | text | yes | `high`, `medium`, `low`, `unknown` |
| `duplicate_group_id` | text | no | Reposts / duplicate discussions |
| `created_at` | timestamptz | yes | Row creation time |

Keys and indexes:

- Primary key: `id`
- Unique candidate: `source + post_id`, if post ID exists
- Index: `ticker, published_at`
- Index: `source, fetched_at`
- Index: `spam_risk, published_at`

Rules:

- Social data is short-term sentiment / attention data, not fundamental evidence.
- Spam, reposts, and duplicate discussions must not count as independent evidence.

## Table: research_logs

使用者研究問題與當時系統輸出摘要。這張表支援未來模型驗證與 User Profile Agent。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `query` | text | yes | User research question |
| `intent` | text | yes | `single_stock_analysis`, `industry_trend`, etc. |
| `ticker` | text | no | Nullable for theme / portfolio queries |
| `theme` | text | no | Theme key or name |
| `decision` | text | no | Main conclusion label |
| `evidence_quality` | text | no | Overall level at query time |
| `price_at_query` | numeric | no | Close/current price used |
| `data_as_of` | date | no | Latest data date used |
| `report_summary` | text | no | Short summary, not full raw response |
| `request_options` | jsonb | no | include_news / include_fundamentals / include_technicals |
| `output_snapshot` | jsonb | no | planned: compact structured output only |
| `created_at` | timestamptz | yes | Query time |

Keys and indexes:

- Primary key: `id`
- Index: `ticker, created_at`
- Index: `intent, created_at`
- Index: `evidence_quality, created_at`

Rules:

- Do not store API keys or secrets.
- Do not store full raw response by default.
- Store enough context to evaluate future 5 / 10 / 20 day outcomes.

## Table: similar_case_results

peer group / market-wide 相似案例查詢結果。這張表可以快取結果，但必須能辨識
freshness，避免使用過期證據。

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key |
| `query_ticker` | text | yes | Ticker being analyzed |
| `query_date` | date | yes | Analysis date |
| `scope` | text | yes | `peer_group`, `market_wide`, `none` |
| `relaxation_step` | text | yes | e.g. `exact_peer_context`, `technical_regime_market` |
| `matched_fields` | text[] | yes | Conditions used |
| `technical_pattern` | text | yes | `breakout`, `volume_surge`, `pullback`, etc. |
| `news_event_type` | text | no | Nullable if relaxed |
| `market_regime` | text | no | Regime used |
| `sample_size` | integer | yes | Number of cases |
| `win_rate_5d` | numeric | no | Forward 5 trading day win rate |
| `win_rate_10d` | numeric | no | Forward 10 trading day win rate |
| `win_rate_20d` | numeric | no | Forward 20 trading day win rate |
| `average_forward_return_20d` | numeric | no | Average 20-day forward return |
| `max_loss_20d` | numeric | no | Worst 20-day forward return |
| `evidence_quality` | text | yes | Peer / market evidence level |
| `source_data_as_of` | date | yes | Latest source data date used |
| `result_status` | text | yes | `fresh`, `stale`, `missing` |
| `created_at` | timestamptz | yes | Result creation time |
| `refreshed_at` | timestamptz | no | Last refresh time |

Keys and indexes:

- Primary key: `id`
- Index: `query_ticker, query_date`
- Index: `scope, relaxation_step`
- Index: `technical_pattern, market_regime`
- Index: `result_status, source_data_as_of`

Rules:

- If underlying `daily_prices`, `technical_features`, `news_events`, or `market_regimes`
  are updated beyond `source_data_as_of`, mark result `stale` or recompute.
- Do not use stale result as current evidence.
- If no matching samples exist, store `scope = none`, `sample_size = 0`,
  `evidence_quality = none`, `result_status = missing`.

## Relationships

```text
tickers
  -> daily_prices
  -> technical_features
  -> news_events
  -> social_events
  -> research_logs

daily_prices
  -> technical_features
  -> similar_case_results

market_regimes
  -> similar_case_results

news_events
  -> similar_case_results

research_logs
  -> future outcome evaluation
```

## Step Mapping

| Step | Uses Tables |
| --- | --- |
| Step 6.2 | Applies all tables to Supabase |
| Step 6.3 | `tickers` |
| Step 6.4 | `daily_prices` |
| Step 6.5 | `technical_features` |
| Step 6.6 | `market_regimes`, `similar_case_results` |
| Step 6.7 | `research_logs` |
| Step 6.8 | `news_events` |
| Step 6.9 | `social_events`, future ML feature mapping |

## SQL Draft Notes

Step 6.2 can turn this markdown into SQL migrations. First migration should include:

- `create extension if not exists pgcrypto;`
- `create table` for all eight core tables.
- Unique constraints listed above.
- Foreign keys where practical.
- Indexes for ticker/date, provider/date, feature flags, status, and event grouping.
- Check constraints for common enum-like fields if Postgres enum type is not used.

No SQL is applied in Step 6.1.
