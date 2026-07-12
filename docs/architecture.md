# Architecture

這份文件說明 Market Agent 目前的系統架構。

Market Agent 的核心設計是 controlled agent workflow。  
它不是讓 LLM 自由決定所有分析步驟，而是由明確的 router 與 manager 控制流程，再把不同分析模組的結果整理成 structured data 與 Research Report。

## 系統總覽

目前系統可以分成五個主要部分：

| 部分 | 用途 |
| --- | --- |
| Frontend | 個人網站上的 MktAgent 頁面，負責輸入問題與展示報告。 |
| API | FastAPI 後端，提供 `/query`、`/backtest`、`/themes` 等 endpoint。 |
| Workflow Manager | `MarketManagerAgent`，負責協調不同分析模組。 |
| Data / ML Pipeline | GitHub Actions 與 scripts，負責更新價格、新聞、基本面、ML prediction 等資料。 |
| Database | Supabase，儲存價格、技術特徵、新聞、基本面、ML prediction 與監控資料。 |

簡化流程：

```text
Frontend
  -> FastAPI /query
  -> Router
  -> MarketManagerAgent
  -> Analysis Modules
  -> Structured Data
  -> Report Builder
  -> Frontend
```

## 為什麼是 Controlled Agent Workflow

這個專案不是讓多個 agent 自由聊天，也不是讓 LLM 直接決定最後答案。

原因是投資研究需要：

- 穩定格式
- 可追蹤資料來源
- 可驗證 structured data
- 固定的風險提醒
- 避免 LLM 任意改寫重要數字

所以目前採用 controlled agent workflow：

1. Router 先判斷問題類型。
2. `MarketManagerAgent` 決定要跑哪些模組。
3. 各模組只負責自己的分析範圍。
4. 系統把結果合併成 structured data。
5. Report Builder 根據 workflow 產生報告。

這樣可以保留 agent workflow 的彈性，同時避免 LLM 自由發揮造成結果不穩。

## 主要元件

### Router

Router 負責判斷使用者問題屬於哪一種 intent。

目前主要 intent：

| Intent | 例子 |
| --- | --- |
| `single_stock_analysis` | `MU 現在適合進場嗎` |
| `industry_trend` | `記憶體類股現在適合進場觀察嗎` |
| `backtest_query` | `MU 突破策略以前表現怎麼樣` |
| `portfolio_analysis` | 投資組合或多檔持股問題 |

Router 採用 hybrid routing。第一層先用 rule-based 判斷 ticker、產業、回測與持有風險等明確問題，並計算 routing confidence。高信心問題直接進入 workflow，不呼叫 LLM；只有低信心、自然語句或混合意圖才透過 OpenRouter 分類。

LLM Router 只回傳經過驗證的 structured JSON，包括 `intent`、`ticker`、`theme`、`strategy`、`question_type`、`confidence` 與 `reason`。它不產生 Research Report，也不能直接改變投資結論。LLM 回傳格式錯誤、未知 ticker/theme 或 provider 暫時失敗時，系統會退回 rule-based 結果或要求使用者補充問題。

Route metadata 會保留 `router_used`、`llm_used`、`fallback_used`、規則信心與判斷原因，方便確認這次問題由哪一層 Router 處理。

### MarketManagerAgent

`MarketManagerAgent` 是目前最主要的 workflow manager。

它負責：

- 選擇分析流程
- 抓取價格資料
- 執行 technical / news / fundamental / backtest / ML reference 等模組
- 整合 evidence quality
- 整合 data freshness
- 整合 exit signal
- 回傳 structured data

它比較像「受控流程編排器」，不是自由對話型 agent。

### Analysis Modules

目前主要分析模組：

| 模組 | 用途 |
| --- | --- |
| Market Data | 取得價格資料，並檢查資料是否足夠。 |
| Technical | 計算均線、RSI、MACD、突破、放量、回踩等訊號。 |
| News | 取得與分類近期新聞，整理情緒、主題與重要性。 |
| Fundamental | 整理基本面資料，例如估值、營收成長、獲利成長與毛利率。 |
| Backtest | 回測 `breakout`、`volume_surge`、`pullback` 等策略。 |
| ML Research | 取得 saved prediction 或 runtime fallback，建立 ML Reference。 |
| Evidence | 整合資料完整度、訊號清楚度、新聞覆蓋、基本面覆蓋等證據品質。 |
| Exit Signal | 針對持有問題產生 `hold`、`watch`、`reduce`、`exit` 觀察訊號。 |

## Query Flow

主要入口是：

```text
POST /query
```

流程：

1. API 收到 `user_query`。
2. Router 判斷 intent。
3. API 根據 intent 呼叫對應 workflow。
4. Workflow 回傳 structured data。
5. Report Builder 產生 Research Report。
6. API 回傳 report、structured data 與 analyst metadata。

## Single Stock Workflow

範例：

```text
MU 現在適合進場嗎
```

主要流程：

1. 解析 ticker。
2. 抓取近一年價格資料。
3. 執行 Technical module。
4. 視選項執行 News module。
5. 視選項執行 Fundamental module。
6. 如果目前出現明確技術訊號，補充歷史訊號回測參考。
7. 建立 Evidence Quality。
8. 建立 ML Reference。
9. 建立 Exit Signal。
10. 建立 Data Freshness。
11. 產生固定格式 Research Report。

Single stock report 目前使用固定格式，避免 LLM 改變版型或關鍵數字。

## Industry / Theme Workflow

範例：

```text
記憶體類股現在適合進場觀察嗎
```

主要流程：

1. Router 判斷這是產業或主題問題。
2. 系統找到對應主題成分股。
3. 對每個成分股執行單股分析。
4. 統整主題內個股分數、技術狀態、新聞與基本面。
5. 聚合 Theme ML Reference。
6. 產生主題研究報告。

Theme workflow 目前可以使用 LLM analyst 整理報告，但仍以 structured data 為基礎。

## Backtest Workflow

範例：

```text
MU 突破策略以前表現怎麼樣
```

主要流程：

1. Router 判斷這是策略回測問題。
2. 選擇策略，例如 `breakout`。
3. 抓取最長可用歷史價格資料。
4. 建立 15 年資料視窗。
5. 執行策略回測。
6. 計算交易次數、勝率、平均報酬與最大虧損。
7. 建立 backtest evidence quality。
8. 產生固定格式 backtest report。

Backtest workflow 不使用 ML Reference。  
前端會顯示 `ML Reference: not used`，這是正常狀態。

## Holding / Exit Workflow

範例：

```text
MU 如果我已經持有，現在要不要減碼
```

這類問題仍走 single stock workflow，但會額外顯示持有風險與出場觀察。

Exit Signal 會根據：

- 技術面是否轉弱
- 是否跌破 MA20
- MACD histogram 是否偏弱
- RSI / MACD 動能
- ML Reference 是否提示 20 日內中途大跌風險

產生：

- `hold`
- `watch`
- `reduce`
- `exit`

這些是持有風險觀察，不是直接交易指令。

## Report Generation

Report Builder 會依照 workflow 產生不同報告。

| Workflow | Report 方式 |
| --- | --- |
| Single Stock | 固定格式 report。 |
| Backtest | 固定格式 report。 |
| Theme | 可使用 LLM analyst，但基於 structured data。 |
| Portfolio | 目前保留，之後會再 redesign。 |

Single stock 與 backtest 使用固定格式，是因為這兩種 report 對數字與章節穩定度要求最高。

Theme report 目前仍可使用 LLM，是因為它比較偏摘要整合，但仍會受到 structured data 限制。

## Data Freshness

Data Freshness 用來提醒本次分析的資料狀態。

Single stock / theme 會檢查：

- daily prices
- technical features
- market regimes
- news events
- ML training data
- pipeline last run

Daily price freshness 使用 expected latest trading day，而不是單純用日曆日期。

如果現在還沒到美股收盤後的預期更新時間，系統會期待「前一個交易日」的 daily price，而不是要求今天資料已經存在。  
這可以避免交易日盤中或資料尚未合理可取得時，System Data 一直顯示 warning。

Backtest 則不同。  
Backtest 的 System Data 代表回測資料視窗的 `data_as_of`，不是即時價格 pipeline 狀態。

## ML Reference

ML Reference 是輔助訊號。

它目前支援：

- saved daily prediction
- runtime fallback
- theme aggregate
- historical return reference
- experimental return model

ML Reference 不會直接改變最後結論或價格計畫。  
如果模型健康度或訊號品質不足，Research Report 會提示降低信任狀態。

## 部署與自動化

目前部署與自動化分工：

| 元件 | 用途 |
| --- | --- |
| Render | 部署 FastAPI 後端。 |
| Supabase | 儲存 production-like 資料。 |
| GitHub Actions | 執行每日價格、新聞、基本面、ML prediction、outcome 與監控流程。 |
| Personal Website | 展示前端 UI。 |

## 現階段限制

目前限制：

- Portfolio workflow 尚未重新設計。
- Peer group / market-wide evidence 尚未完整接入 report。
- ML Reference 仍是輔助訊號，不是正式投資模型。
- 新聞資料目前主要來自新聞來源，社群資料尚未納入。
- Report 不提供投資建議，也不執行交易。
