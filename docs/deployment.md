# Deployment

這份文件說明 Market Agent 目前如何部署，以及本地、GitHub Actions、Supabase、Render 和前端各自負責什麼。

## 解釋

Market Agent 的部署方式是：

```text
GitHub Actions 更新資料 -> Supabase 儲存資料 -> Render 提供後端 API -> 個人網站前端顯示結果
```

Render 不是主要資料更新器。  
正式資料更新主要由 GitHub Actions 排程完成。

> 這個專案不是只在本地跑。後端部署在 Render，資料存在 Supabase，GitHub Actions 會定期更新價格、新聞、基本面和 ML predictions。前端可以切到部署後的 API，所以展示時看到的是接近 production 的資料流。

## 系統分工

| 元件 | 負責工作 |
| --- | --- |
| 本地環境 | 開發、測試、手動跑 pipeline。 |
| GitHub Actions | 定期更新資料、計算 outcomes、產生 monitoring、寄錯誤信。 |
| Supabase | 儲存價格、技術特徵、新聞、基本面、ML predictions、outcomes。 |
| Render | 部署 FastAPI 後端，提供 `/query` 等 API。 |
| 個人網站前端 | 呼叫後端 API，展示 Research Report 與 Structured Data。 |

## Render 後端

Render 部署的是 FastAPI backend。

主要用途：

- 接收前端 query。
- 路由到 single stock、theme、backtest、holding-risk workflow。
- 從 Supabase 讀最新資料。
- 必要時呼叫 provider fallback。
- 產生 structured data 和 Research Report。

Render 不適合負責大量每日資料更新，因為免費方案資源有限，也不應該把長時間 pipeline 放在 request path 裡。

## GitHub Actions

GitHub Actions 負責排程資料更新。

目前主要 workflow：

- `daily-prices.yml`
- `daily-news.yml`
- `daily-outcomes.yml`
- `daily-ml-predictions.yml`
- `daily-research-fixtures.yml`
- `weekly-research-fixtures.yml`
- `weekly-ml-dataset.yml`
- `monthly-universe.yml`

詳細排程與資料流程請看：

```text
docs/data_pipeline.md
```

## Supabase

Supabase 是主要資料庫。

它讓 Render 後端不需要每次 query 都重新抓完整資料。

主要儲存：

- universe / tickers
- daily prices
- technical features
- market regimes
- fundamental snapshots
- news events
- ML predictions
- prediction outcomes
- research logs
- research outcomes
- pipeline runs

## 必要環境變數

後端和 GitHub Actions 需要以下 secrets。

```env
MARKET_AGENT_ANALYST_MODE=llm
MARKET_AGENT_LLM_PROVIDER=openrouter
MARKET_AGENT_LLM_MODEL=openai/gpt-4.1
OPENROUTER_API_KEY=
OPENROUTER_APP_NAME=market-agent

NEWS_EXTRACTOR_MODE=rule_based
NEWS_LLM_PROVIDER=openrouter
NEWS_LLM_MODEL=openai/gpt-5.4-mini
NEWS_LLM_ESCALATION_ENABLED=false
NEWS_LLM_ESCALATION_MODEL=openai/gpt-5.5

SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=

ALERT_EMAIL_ENABLED=
ALERT_EMAIL_FROM=
ALERT_EMAIL_TO=
GMAIL_APP_PASSWORD=
```

## 部署後遇到的狀況

### 本地和 Render 回答不同

常見原因：

- 本地有 `.env` 或本地資料，Render 沒有。
- Render secrets 沒設完整。
- Supabase 資料尚未更新。
- GitHub Actions 還沒跑完最新 pipeline。
- LLM analyst 在不同時間生成文字時，語句可能略有不同。

### System Data 是 warning

常見原因：

- 還沒到當天預期市場資料更新時間。
- pipeline 已超過 24 小時但未超過 stale 門檻。
- 某些非核心資料稍微延遲。

### System Data 是 stale / missing

應先檢查：

1. GitHub Actions 是否失敗。
2. Supabase secrets 是否正確。
3. `pipeline_runs` 是否有最新成功紀錄。
4. 價格資料是否已更新到預期交易日。

### 收到錯誤信

錯誤信通常代表：

- provider 暫時不可用
- Supabase 寫入失敗
- freshness check 發現資料過舊
- ML health degraded
- GitHub Actions workflow 失敗

錯誤信不是壞事，代表系統有監控到問題。

## Demo 前檢查清單

- Render backend `/health` 正常。
- GitHub Actions 最近一次 daily prices 成功。
- GitHub Actions 最近一次 daily ML predictions 成功。
- Supabase 有最新 `daily_prices` 和 `technical_features`。
- 前端可以成功送出 query。
- `System Data` 至少不是 `stale` / `missing`。
- 四個 demo 問題能正常回應。

## Takeaways

- Render 負責 API，不負責大量排程資料更新。
- GitHub Actions 負責自動更新資料。
- Supabase 是 production-like 資料中心。
- 錯誤信和 health report 是部署後維護的重要部分。
- 本地測試成功不代表 Render 一定完全相同，必須檢查 secrets 和 Supabase 資料。
