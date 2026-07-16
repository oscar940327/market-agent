# Data Pipeline

這份文件說明 Market Agent 的資料如何進入系統、如何寫入 Supabase，以及前端的 `System Data` 狀態從哪裡來。

## 核心概念

Market Agent 不應該每次使用者問問題時才從零開始抓所有資料。

目前設計是：

1. GitHub Actions 定期更新資料。
2. 資料寫入 Supabase。
3. Render 後端查 Supabase 與必要 provider。
4. 前端顯示 Research Report 與資料狀態。

這樣做的目的，是讓 demo 和正式使用時的結果更穩定，也能知道資料是否過期。

## 主要資料

| 資料 | Supabase 表 | 主要用途 |
| --- | --- | --- |
| 股票清單 | `tickers` | QQQ100 / theme universe |
| 每日價格 | `daily_prices` | 技術分析、回測、ML features |
| 技術特徵 | `technical_features` | MA、RSI、MACD、breakout、volume surge、pullback |
| 市場環境 | `market_regimes` | QQQ market regime、ML feature、context |
| 基本面快照 | `fundamental_snapshots` | Forward P/E、營收成長、獲利成長、毛利率等 |
| 新聞事件 | `news_events` | 新聞情緒、主題、重要性 |
| 新聞摘要 | `news_event_summaries` | 30 日新聞摘要與 theme summary |
| ML predictions | `ml_predictions` | 每日 5 / 10 / 20 日上漲機率與大跌風險 |
| ML prediction outcomes | `ml_prediction_outcomes` | 成熟後的真實結果，用於 metrics / calibration |
| Research logs | `research_logs` | 每次固定測資或重要研究問題的 report snapshot |
| Research outcomes | `research_outcomes` | Research Report 成熟後的真實價格結果 |
| Pipeline runs | `pipeline_runs` | 每次自動化流程的狀態與錯誤紀錄 |

## GitHub Actions 排程

下表用台灣時間表示，方便閱讀。  
GitHub Actions 實際設定仍是 UTC cron，且不會自動依照美國日光節約時間調整。

| Workflow | 台灣時間 | UTC cron | 主要工作 |
| --- | --- | --- | --- |
| `daily-prices.yml` | 週二到週六 `06:15` | 週一到週五 `22:15 UTC` | 更新 QQQ、QQQ100 價格、技術特徵、市場環境、基本面 |
| `daily-news.yml` | 週二到週六 `07:30` | 週一到週五 `23:30 UTC` | 抓新聞、分類新聞、產生新聞摘要 |
| `daily-outcomes.yml` | 週二到週六 `08:15` | 週二到週六 `00:15 UTC` | 計算成熟 research outcomes、ML prediction outcomes、metrics、calibration、ML health |
| `daily-ml-predictions.yml` | 週二到週六 `09:30` | 週二到週六 `01:30 UTC` | 建立最新 ML dataset artifact、similar-case accumulation、每日 ML predictions |
| `daily-research-fixtures.yml` | 週二到週六 `09:45` | 週二到週六 `01:45 UTC` | 執行四個固定測資、寫入 research logs / outcomes、寄出 daily research report |
| `weekly-research-fixtures.yml` | 週六 `10:30` | 週六 `02:30 UTC` | 執行 NVDA、AAPL、半導體主題、MU 放量與拉回策略測資，寄出 weekly research report |
| `weekly-ml-dataset.yml` | 週日 `13:00` | 週日 `05:00 UTC` | 建立 weekly ML dataset 與完整 monitoring reports |
| `monthly-universe.yml` | 每月 1 日 `14:00` | 每月 1 日 `06:00 UTC` | 更新 QQQ100 / Nasdaq-100 universe |

所有排程完成後都會執行 rule-based maintenance diagnosis，並將 JSON / Markdown 報告放入 workflow artifact。失敗、partial success、degraded、stale 或 missing 狀態會建立或更新 GitHub Issue；相同 fingerprint 只更新原 Issue，不會每天重複建立。

完整說明：[Automation and Self-Maintenance](automation_maintenance.md)

價格資料通常安排在美股收盤後約 2 小時更新。  
新聞排程放在價格更新之後，因為盤後新聞通常比較密集。

## Daily Prices Pipeline

執行指令：

```bash
python scripts/run_daily_pipeline.py --only prices
```

主要步驟：

1. `benchmark_prices`
   - 更新 QQQ 價格。
2. `daily_prices`
   - 更新 universe 股票價格。
   - 目前是補齊 Supabase 缺少或需要更新的每日 OHLCV，不是每天重抓完整 15 年資料。
3. `benchmark_technical_features`
   - 計算 QQQ 技術特徵。
4. `technical_features`
   - 計算 universe 股票技術特徵。
5. `market_regimes`
   - 用 QQQ 判斷市場環境。
6. `freshness_check`
   - 檢查價格、技術特徵、市場環境是否同步。

## Fundamentals Pipeline

執行指令：

```bash
python scripts/run_daily_pipeline.py --only fundamentals
```

主要工作：

- 從 provider 抓基本面資料。
- 寫入 `fundamental_snapshots`。
- Render 後端分析單股與 theme 時，會優先讀 Supabase 的最新基本面快照。

目前基本面資料是輔助研究資料，不是完整財報資料庫。

## News Pipeline

執行指令：

```bash
python scripts/run_daily_pipeline.py --only news
```

主要步驟：

1. `news_ingestion`
   - 抓 Google News RSS / yfinance news 等免費來源。
   - 寫入 `news_events`。
2. `news_classification`
   - 分類 sentiment、topic、importance、ticker relevance。
   - 預設可以用 rule-based；LLM extractor 是 optional。
3. `news_summary`
   - 產生 30 日新聞摘要。
   - 寫入 `news_event_summaries`。

新聞資料目前用來影響 Research Report 的新聞面分析，但不應單獨決定結論。

## ML Prediction Pipeline

執行 workflow：

```text
Daily ML Predictions
```

主要步驟：

1. 建立最新 ML training dataset artifact。
2. 建立 similar-case accumulation。
3. 針對 universe 產生每日 ML predictions。
4. 寫入 `ml_predictions`。

這裡的 prediction 是每天用最新資料做 inference / reference。  
它不代表每天重新訓練模型。

## Outcome Pipeline

執行 workflow：

```text
Daily Research Outcomes
```

主要工作：

- 計算成熟的 research outcomes。
- 計算成熟的 ML prediction outcomes。
- 建立 ML monitoring metrics。
- 建立 calibration report。
- 建立 model upgrade review。
- 建立 ML health report。

### 什麼是成熟 outcome

如果某筆 prediction 是在 `2026-07-01` 產生：

- 5 trading-day outcome 要等 5 個交易日後才成熟。
- 10 trading-day outcome 要等 10 個交易日後才成熟。
- 20 trading-day outcome 要等 20 個交易日後才成熟。

成熟的意思是：Supabase 已經有足夠的後續價格資料，可以計算真實結果。

未成熟不代表模型壞掉，只代表時間還沒到。

### Outcome 狀態

| 狀態 | 意思 |
| --- | --- |
| `pending` | 還沒到 target date，不能計算。 |
| `computed` | 已有足夠價格資料，結果已算出並寫回 Supabase。 |
| `missing_price` | target date 已到，但缺少價格資料。 |
| `skipped` | 這個 workflow 不適用或沒有可計算資料。 |

## System Data Freshness

前端的 `System Data` badge 來自 backend 的 `data_freshness`。

主要檢查：

| 項目 | 檢查內容 |
| --- | --- |
| `daily_prices` | 最新價格是否達到預期最新交易日。 |
| `technical_features` | 是否和 `daily_prices` 同步。 |
| `market_regimes` | 是否和 `daily_prices` 同步。 |
| `news_events` | 最近 30 天內是否有新聞。 |
| `fundamental_snapshots` | 最新基本面 snapshot 是否可用。 |
| `ml_training_data` | ML dataset 是否在 7 天內更新。 |
| `pipeline_last_run` | pipeline 是否最近有成功執行紀錄。 |

整體狀態：

| 狀態 | 意思 |
| --- | --- |
| `fresh` | 目前資料可正常使用。 |
| `warning` | 可以使用，但要留意資料可能稍微落後或部分流程需要檢查。 |
| `stale` | 資料過舊，Research Report 應保守解讀。 |
| `missing` | 缺少必要資料。 |

每次單股研究也會產生 `data_recovery`。它會區分問題是否影響本次 Research Report，並提供對應 pipeline 或檢查命令。第一版只提供建議，不會自動執行修復。

ML dataset freshness 優先讀取 Supabase `ml_dataset_metadata`，本地 metadata 檔案只作為 fallback。這可以避免 GitHub Actions 已更新 dataset，但 Render 仍因本地舊檔案顯示 stale。

## 交易日當天為什麼不一定 warning

美股交易日當天，收盤前或剛收盤時，provider 不一定已經提供完整日線資料。

因此系統不會單純用今天日期判斷資料是否過期，而是使用 expected latest trading day：

- 如果還沒到預期市場資料更新時間，允許沿用上一個交易日資料。
- 如果已經過了預期更新時間，才要求今日交易日資料出現。
- 週末與假日會自動使用上一個實際交易日。

目前預期更新時間約是美東時間 18:00。

## 本地、GitHub Actions、Render 的分工

| 環境 | 負責什麼 |
| --- | --- |
| 本地 | 開發、測試、手動跑 pipeline、檢查修正。 |
| GitHub Actions | 定期更新 Supabase、產生 monitoring artifact、寄錯誤信。 |
| Render | 提供後端 API，讀 Supabase 資料並回應前端。 |
| 個人網站前端 | 呼叫後端 API，展示 Research Report 與 Structured Data。 |

Render 本身不應負責每天大量抓資料。  
正式資料更新主要交給 GitHub Actions。

## 手動測試指令

更新價格與技術資料：

```bash
python scripts/run_daily_pipeline.py --only prices
```

只測幾檔：

```bash
python scripts/run_daily_pipeline.py --only prices --tickers MU,NVDA,AAPL
```

更新基本面：

```bash
python scripts/run_daily_pipeline.py --only fundamentals
```

只更新 MU 基本面：

```bash
python scripts/run_daily_pipeline.py --only fundamentals --tickers MU
```

更新新聞：

```bash
python scripts/run_daily_pipeline.py --only news
```

檢查 freshness：

```bash
python scripts/check_freshness.py --json
```

只檢查共享 ML dataset metadata：

```bash
python scripts/check_freshness.py --scope ml_training --json
```

詳細 recovery 欄位請見 [Data Recovery](data_recovery.md)。

## 常見狀況

### System Data 是 warning

通常代表：

- 價格資料落後一個交易日。
- pipeline 超過 24 小時沒有成功執行。
- 某些非核心資料稍微延遲。

如果 Research Report 已顯示 warning，demo 時仍可使用，但要保守解讀。

### System Data 是 stale / missing

代表資料過舊或缺少必要資料。

優先檢查：

1. GitHub Actions 是否失敗。
2. Supabase secrets 是否正確。
3. provider 是否暫時不可用。
4. `pipeline_runs` 是否有最近成功紀錄。

### ML Reference 是 fallback

通常代表找不到可用的 saved daily prediction，系統改用 runtime fallback。  
這不一定是錯誤，但正式 demo 時最好讓 `daily-ml-predictions` workflow 成功跑過。

### ML Reference 是 skipped

代表該 workflow 不使用 ML Reference。  
例如策略回測問題主要看歷史交易結果，不需要 ML Reference。
