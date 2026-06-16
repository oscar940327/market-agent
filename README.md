# Market Agent

Market Agent 是一個個人股票研究 API，用來整理單股、主題類股、回測與投資組合風險資訊。

它的定位是研究輔助工具，不是自動交易系統，也不提供買賣建議。

## Features

- 單一股票分析：整理價格趨勢、均線、突破、成交量與回測區訊號。
- 主題股票掃描：支援記憶體、AI server、半導體、大型科技、資安、雲端、能源、醫療等分類。
- 策略回測：支援 `breakout`、`volume_surge`、`pullback`。
- 投資組合研究：分析持股權重、集中度、主題曝險與 portfolio-level risk。
- 多資料源價格 fallback：目前支援 `yfinance` 與 `Stooq`。
- Controlled agent workflow：由 `MarketManagerAgent` 編排 Technical / News / Fundamental / Backtest / Portfolio agents。
- Analyst report：支援 rule-based report，也可選用 LLM Analyst。
- LLM fallback：LLM 未設定或失敗時會自動回到 rule-based report。

## API

主要 endpoints：

- `GET /health`
- `POST /route`
- `POST /query`
- `POST /analyze/single`
- `POST /backtest`
- `POST /themes`
- `POST /portfolio`

`POST /query` 是統一入口，會先判斷問題類型，再呼叫對應 workflow。

## Examples

單股分析：

```json
{
  "ticker": "MU",
  "user_query": "現在適合進場嗎？",
  "include_news": false,
  "include_fundamentals": false,
  "analyst_mode": "rule_based"
}
```

主題掃描：

```json
{
  "user_query": "資安股有哪些值得觀察？",
  "analyst_mode": "rule_based"
}
```

投資組合研究：

```json
{
  "user_query": "我目前持有 VOO QQQM TSLA 有什麼需要注意？",
  "holdings": [
    {"ticker": "VOO", "market_value": 5000},
    {"ticker": "QQQM", "market_value": 3000},
    {"ticker": "TSLA", "market_value": 2000}
  ],
  "include_news": false,
  "include_fundamentals": false,
  "analyst_mode": "rule_based"
}
```

## Website Integration

本專案主要是搭配個人網站的 `MktAgent` 頁面使用。

前端頁面負責輸入與展示，後端 `market-agent` 負責分析與回傳 report。

## Not In Scope

- 自動交易
- 下單功能
- 投資保證
- 買入 / 賣出 / 持有絕對建議

## Disclaimer

本專案僅供個人研究與程式開發使用，不構成任何投資建議。金融市場具有風險，任何交易決策都應自行評估並承擔結果。
