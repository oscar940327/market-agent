# Market Agent

Market Agent 是一個個人股票研究 Agent 專案，目標是用自然語言協助整理市場資料、技術訊號、策略條件與歷史回測結果。

這個專案目前已具備 V3 controlled agentic workflow：單一股票分析、三種策略回測查詢、主題股票觀察清單、多面向研究資料，以及 Manager + Expert Agents 架構。

## What It Is

Market Agent 預計支援這類問題：

- `MU 現在適合進場嗎？`
- `目前記憶體概念股趨勢如何？`
- `某檔股票現在是突破還是追高？`
- `這個技術訊號以前回測表現怎麼樣？`

Agent 的角色是理解問題、拆解任務，並呼叫明確的 Python 模組取得資料、計算指標、套用策略規則或讀取回測結果。LLM 目前尚未接入，現階段由 rule-based analyst 將結構化資料整理成中文研究摘要。

## What It Is Not

Market Agent 不是：

- 自動交易系統
- 投資保證工具
- 下單機器人
- 財務或投資建議服務

所有輸出都應視為研究輔助資訊，不應直接作為買賣決策。

## Design

本專案採用 controlled agentic workflow。

也就是說，Agent 不會完全自主決定所有事情，而是負責：

1. 理解使用者問題
2. 判斷問題類型
3. 選擇要呼叫的 skill 或 strategy
4. 整合模組輸出的結果
5. 回覆可讀的研究摘要

V3 之後，流程由 `MarketManagerAgent` 編排：

```text
使用者問題
↓
Market Manager Agent
↓
Technical Agent
News Agent
Fundamental Agent
Backtest Agent
↓
Market Manager Agent
↓
Analyst
↓
自然語言研究回答
```

實際資料取得、技術分析、新聞整理、基本面摘要、策略判斷與回測讀取，會交給明確、可測試的 Python 模組處理。

## Project Structure

```text
market-agent/
├── agent/
│   ├── analyst.py
│   ├── market_manager.py
│   ├── research_profile.py
│   ├── rule_based_router.py
│   └── experts/
│       ├── technical_agent.py
│       ├── news_agent.py
│       ├── fundamental_agent.py
│       └── backtest_agent.py
│
├── skills/
│   ├── stock_price_skill.py
│   ├── technical_analysis_skill.py
│   ├── news_skill.py
│   ├── news_analysis_skill.py
│   └── fundamental_skill.py
│
├── data_providers/
│   ├── price_service.py
│   ├── yfinance_provider.py
│   └── stooq_provider.py
│
├── strategies/
│   ├── breakout_strategy.py
│   ├── pullback_strategy.py
│   └── volume_surge_strategy.py
│
├── backtesting/
│   ├── backtest_runner.py
│   ├── metrics.py
│   └── reports.py
│
├── data/
│   ├── themes.py
│   └── historical_prices/
│
├── api.py
├── main.py
├── requirements.txt
├── schedule/
└── README.md
```

## Planned Modules

### Agent

負責自然語言問題理解、流程控制與研究結果整合，例如：

- 判斷使用者是在問單一股票、族群趨勢、技術訊號或回測表現
- 建立 execution plan
- 決定要呼叫哪些 expert agents
- 將 technical、news、fundamental、backtest 結果整理成穩定 `analysis_data`
- 將結構化資料交給 analyst 產生可讀報告

### Expert Agents

目前支援：

- `Technical Agent`：均線、趨勢、breakout、volume surge、pullback
- `News Agent`：新聞取得、topic、sentiment、importance
- `Fundamental Agent`：估值、成長、現金流、風險摘要
- `Backtest Agent`：策略選擇、歷史勝率、平均報酬、最大虧損

### Skills

放置具體、可重複使用的能力，例如：

- 抓取或讀取股價資料
- 計算均線、成交量、突破區間等技術指標
- 整理新聞或基本市場資訊
- 格式化輸出結果

### Strategies

放置明確的策略規則，例如：

- 是否突破 20 日高點
- 成交量是否明顯放大
- 是否回測 MA20 後反彈
- 是否接近支撐或壓力區

### Backtesting

回測模組預計用來事先處理歷史資料，將策略表現整理成可查詢結果。

預期流程：

```text
歷史資料
↓
策略規則
↓
回測結果
↓
儲存摘要
↓
使用者提問時讀取結果
```

目前已建立 `backtesting/` 目錄，並支援 breakout、volume_surge、pullback 三種策略的簡單離線回測。

## Version History

- `V1`: 建立 CLI / API core，支援單股分析、策略回測與主題掃描。
- `V2`: 加入多資料源價格、新聞結構化、基本面摘要與綜合研究 profile。
- `V3`: 加入 Market Manager 與 Technical / News / Fundamental / Backtest expert agents。

## Current Status

目前進度：

- 已建立基本專案骨架
- 已建立 `agent/`、`agent/experts/`、`skills/`、`strategies/`、`backtesting/`、`data/` 目錄
- `main.py` 已作為 CLI 入口
- 已定義 `yfinance`、`pandas`、`python-dotenv` 依賴
- 已支援單一股票分析 workflow
- 已支援 breakout、volume_surge、pullback 策略回測查詢初版
- 已支援固定主題股票池掃描
- 已支援 rule-based 分析報告輸出
- 已支援 `yfinance + Stooq` 多資料源股價 fallback
- 已支援穩定 API response schema：`status`、`intent`、`data`、`report`、`error`
- 已支援新聞結構化摘要：topic、sentiment、importance
- 已支援基本面資料摘要
- 已支援主題 / 同業廣度摘要
- 已支援綜合研究 profile：technical、news、fundamental、risk、setup quality
- 已支援 `MarketManagerAgent` 編排單股分析與回測查詢
- 已支援 Technical / News / Fundamental / Backtest expert agent outputs
- 已支援 `execution_plan` 與 `agent_outputs`
- 尚未接 LLM analyst、資料庫或 Web UI
- 自動通知、自動交易與下單功能不在目前產品範圍

## Development

安裝依賴後可以用 CLI 執行：

```bash
python main.py
```

目前 CLI 會輸出固定格式研究摘要，先不接 LLM。

也可以啟動 FastAPI backend，供未來網站或其他 client 呼叫：

```bash
uvicorn api:app --reload
```

目前 API endpoint：

- `GET /health`
- `POST /route`
- `POST /query`
- `POST /analyze/single`
- `POST /backtest`
- `POST /themes`

`POST /query` 是給網站整合用的統一入口，會先判斷 intent，再呼叫對應 workflow。範例：

```json
{
  "user_query": "MU 現在適合進場嗎？",
  "include_news": true,
  "include_fundamentals": true
}
```

本地測試：

```bash
python -m pytest -q
```

目前測試狀態：

```text
38 passed
```

## Disclaimer

本專案僅供個人研究與程式開發使用，不構成任何投資建議。金融市場具有風險，任何交易決策都應自行評估並承擔結果。
