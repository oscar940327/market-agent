# Architecture

這份文件說明 Market Agent 目前的系統架構。

Market Agent 的核心設計是 controlled agent workflow。  
Router 與既有 manager 先建立可驗證的 structured data；啟用 Agentic mode 時，再由受限的 LLM Orchestrator 與專業 Agent 規劃研究動作。所有 Agent 都受工具白名單、schema、步數與 read-only 權限控制。

## 系統總覽

目前系統可以分成五個主要部分：

| 部分 | 用途 |
| --- | --- |
| Frontend | 個人網站上的 MktAgent 頁面，負責輸入問題與展示報告。 |
| API | FastAPI 後端，提供 `/query`、`/backtest`、`/themes` 等 endpoint。 |
| Workflow Manager | `MarketManagerAgent`，負責協調不同分析模組。 |
| Agentic Orchestration | Research Orchestrator 與專業 Agent，負責受控規劃、資料缺口檢查和觀點整合。 |
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
  -> Agentic Orchestrator / Specialist Agents
  -> Report Builder
  -> Frontend
```

## 為什麼是 Controlled Agent Workflow

這個專案不是讓多個 agent 自由聊天，也不是讓 LLM 直接決定最後答案。Agentic mode 允許 LLM 選擇白名單內的研究步驟，但不能計算或改寫原始數字。

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

### Agentic Research Orchestrator

啟用 `MARKET_AGENT_ORCHESTRATOR_MODE=llm` 後，Research Orchestrator 會根據問題類型與前端選取範圍建立 execution plan，再呼叫 Technical、Fundamental、News、ML、Theme 與 Risk 等專業 Agent。

每個 Agent 只能讀取 allowlist 內的 tools，並回傳 `specialist_output_v1`。系統會驗證 status、confidence、evidence references 與 missing data；資料不足時最多進行設定次數內的唯讀補查。錯誤時回到 deterministic workflow，並在 `agentic_orchestration` 留下 fallback 與 decision trace。

詳細邊界與環境設定見 [Agentic Orchestration](agentic_orchestration.md)。

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

### Analyst Outputs

Single-stock 與 theme workflow 會把既有分析結果轉成統一的 `analyst_outputs`：technical、fundamental、news、ML 與 risk。每個 Analyst 都使用相同的 `analyst_output_v1` contract：

```json
{
  "schema_version": "analyst_output_v1",
  "analyst": "technical_analyst",
  "status": "success",
  "stance": "negative",
  "confidence": "medium",
  "key_evidence": [],
  "limitations": [],
  "warning_flags": []
}
```

`key_evidence` 的每筆資料都有 `field`、`value` 與 `source`，可以追溯到原始 Structured Data。`analyst_consensus` 只整理各 Analyst 的 stance 與衝突，不重新產生投資判斷。第一版由既有 deterministic analysis 建立，不增加 LLM token；Step 25 Reviewer 將以這些輸出作為檢查輸入。

### Report Review Layer

Research Report 產生後會先經過 deterministic reviewer，檢查必要段落、問題類型、ML trust、資料 freshness、關鍵機率、風險聲明與過度自信語句。結果會寫入 `report_review`，並包含 checks、risk notes、suggested fixes、iteration history 與 fallback 狀態。

當 `MARKET_AGENT_REPORT_REVIEW_MODE=hybrid` 且 deterministic review 未通過時，才會啟動 OpenRouter reviewer/reviser：

每日固定 fixture 使用 `MARKET_AGENT_REPORT_REVIEW_MODE=hybrid`，每週 fixture 使用 `semantic`。LLM reviewer 會對 query relevance、evidence consistency、risk balance、clarity、hallucination safety 與 overall quality 各給 1～5 分；所有已執行的 semantic 分數至少 4 分才可通過，不合格時最多修訂 2 次。

```text
Draft Report
  -> Deterministic Review
  -> LLM Semantic Review
  -> LLM Revision
  -> Deterministic Recheck
  -> Final LLM Review
```

通過就立即停止，最多三輪；最壞情況為每輪 reviewer + reviser，共六次 LLM 呼叫。Reviser 只能根據 Structured Data 與 review findings 修正文句，不得修改 structured values 或新增投資判斷。LLM 不可用或達到上限仍未通過時，系統保留目前報告並輸出 review warning。

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
6. Review Layer 檢查報告，必要時進行受控修正。
7. API 回傳 report、structured data、analyst metadata 與 review metadata。

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
11. 啟用 Agentic mode 時，由 Report Writer 使用已驗證的專業輸出組成報告；否則產生固定格式 Research Report。

無論採用哪種模式，Report Writer 都不能改變 structured values，且輸出仍會經過 Number Validator 與 Review Layer。

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
- fundamental snapshots

Step 29 在 freshness 後加入 deterministic Data Recovery policy。它把每個缺口轉成 `report_impact`、`affected_output` 與 `recommended_action`，並區分當次報告問題和單純維護問題。第一版不會自動執行 recovery。

ML dataset metadata 會由 weekly workflow 寫入 Supabase，Render、GitHub Actions 與本地優先讀取同一份 shared metadata；本地 JSON 只作為 fallback。

Step 30 新增受控模型 promotion lifecycle。每月 workflow 會重新執行 Step 28，候選模型通過初選後才建立 shadow predictions。Shadow 與 production 共用 outcome tracking，但正式查詢固定只讀 production；系統能提出 `promote_candidate`，卻不會自動替換正式模型。

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
