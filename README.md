# Market Agent

Market Agent 是一個個人股票研究 Agent 專案，目標是用自然語言協助整理市場資料、技術訊號、策略條件與歷史回測結果。

這個專案目前已具備第一版 CLI 核心：單一股票分析、三種策略回測查詢、主題股票觀察清單，以及 rule-based 文字報告。

## What It Is

Market Agent 預計支援這類問題：

- `MU 現在適合進場嗎？`
- `目前記憶體概念股趨勢如何？`
- `某檔股票現在是突破還是追高？`
- `這個技術訊號以前回測表現怎麼樣？`

Agent 的角色是理解問題、拆解任務，並呼叫明確的 Python 模組取得資料、計算指標、套用策略規則或讀取回測結果。

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

實際資料取得、技術分析、策略判斷與回測讀取，會交給明確、可測試的 Python 模組處理。

## Project Structure

```text
market-agent/
├── agent/
│   ├── analyst.py
│   └── rule_based_router.py
│
├── skills/
│   ├── stock_price_skill.py
│   ├── technical_analysis_skill.py
│   └── news_skill.py
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
├── main.py
├── requirements.txt
├── current_progress.md
├── project_context.md
└── README.md
```

## Planned Modules

### Agent

負責自然語言問題理解與流程控制，例如：

- 判斷使用者是在問單一股票、族群趨勢、技術訊號或回測表現
- 決定要呼叫哪些 skills
- 將資料、策略與回測結果整理成回覆

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

## Current Status

目前進度：

- 已建立基本專案骨架
- 已建立 `agent/`、`skills/`、`strategies/`、`backtesting/`、`data/` 目錄
- `main.py` 已作為 CLI 入口
- 已定義 `yfinance`、`pandas`、`python-dotenv` 依賴
- 已支援單一股票分析 workflow
- 已支援 breakout、volume_surge、pullback 策略回測查詢初版
- 已支援固定主題股票池掃描
- 已支援 rule-based 分析報告輸出
- 尚未接 LLM analyst、資料庫、Web UI 或自動通知

## Development

安裝依賴後可以用 CLI 執行：

```bash
python main.py
```

目前 CLI 會輸出固定格式研究摘要，先不接 LLM。

## Disclaimer

本專案僅供個人研究與程式開發使用，不構成任何投資建議。金融市場具有風險，任何交易決策都應自行評估並承擔結果。
