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

## Level Rules

這一節集中說明系統裡會出現的等級。這些等級用來描述資料品質、訊號清楚度、
風險或歷史樣本強弱，不是投資建議本身。

### Common Scale

| 等級 | 意思 |
| --- | --- |
| `high` | 資料或訊號相對充足，參考價值較高。 |
| `medium` | 有一定參考價值，但仍有缺口或風險。 |
| `low_to_medium` | 有一些參考價值，但證據還偏薄。 |
| `low` | 參考價值有限，需要保守看待。 |
| `none` | 沒有可用資料或沒有符合條件的樣本。 |
| `skipped` | 使用者本次主動沒有勾選該資料來源。 |
| `not_used` | 系統目前尚未實作或尚未使用該資料來源。 |
| `not_applicable` | 這個欄位不適用於本次 workflow。 |
| `unknown` | 系統無法判斷狀態。 |

### Research Evidence Quality

Evidence quality 是多個面向的總結，包含個股資料、歷史訊號樣本、資料完整度、
技術訊號清楚度、新聞覆蓋、情緒信心、新聞影響品質、基本面覆蓋，以及未來的
peer / market evidence。

主要分項規則：

| 欄位 | 規則 |
| --- | --- |
| `stock_specific` | 個股價格資料 >= 200 筆為 `medium`，60-199 筆為 `low_to_medium`，少於 60 筆為 `low`。 |
| `price_data_coverage` | 價格資料 >= 200 筆為 `high`，60-199 筆為 `medium`，20-59 筆為 `low_to_medium`，少於 20 筆為 `low`，無資料為 `none`。 |
| `news_coverage` | 未勾選新聞為 `skipped`；0 篇為 `none`；1 篇為 `low_to_medium`；2 篇為 `medium`；3 篇以上為 `high`。 |
| `sentiment_confidence` | 新聞 3 篇以上且主要情緒占比 >= 67% 為 `high`；2 篇以上且主要情緒占比 >= 50% 為 `medium`；其餘為 `low_to_medium`。 |
| `news_impact_quality` | 高重要性新聞 >= 2 且有明確主題為 `high`；至少 1 篇高重要性新聞或有明確主題為 `medium`；其餘為 `low_to_medium`。 |
| `fundamental_coverage` | 未勾選基本面為 `skipped`；抓不到為 `none`；有效基本面數據 >= 6 項為 `high`，3-5 項為 `medium`，少於 3 項為 `low_to_medium`。 |
| `signal_clarity` | 技術訊號越一致越高；訊號互相衝突會降低等級。 |
| `social_coverage` | 社群資料尚未接入前固定為 `not_used`。 |
| `peer_group` / `market_wide` | production workflow 尚未接入相似案例查詢前，仍顯示 `not_used`。 |

整體 `level` 會把可用分項換算成分數平均：

| 平均分數 | 等級 |
| --- | --- |
| >= 3.5 | `high` |
| >= 2.5 | `medium` |
| >= 1.5 | `low_to_medium` |
| > 0 | `low` |
| 0 | `none` |

### Backtest Evidence

| 欄位 | 規則 |
| --- | --- |
| `sample_quality` | 0 筆為 `none`；1-4 筆為 `very_low`；5-9 筆為 `low`；10-29 筆為 `medium`；30 筆以上為 `high`。 |
| `market_cycle_coverage` | 個股歷史資料達 15 年為 `sufficient`，未達 15 年為 `insufficient`。 |
| `loss_risk` | 最大虧損 >= -8% 為 `controlled`；-15% 到 -8% 為 `medium`；低於 -15% 為 `high`。 |

Backtest 的整體 evidence level：

- 沒有樣本：`none`
- 歷史未達 15 年：最多只給到 `low_to_medium`
- 樣本品質高、勝率 >= 50%、平均報酬為正、最大虧損受控：`high`
- 樣本品質中等以上且平均報酬為正：`medium`
- 樣本品質至少不是太低，但條件不夠完整：`low_to_medium`
- 其他情況：`low`

### Peer / Market Evidence

第一版 peer / market universe 以 provider 提供的 QQQ100 / QQQ holdings 成分股為主。
`data/themes.py` 可作為本地股票主題分類、seed 與 fallback 參考，但不取代 provider 成分股來源。

`peer_group` 與 `market_wide` 分開判斷：

- `peer_group`：同產業、同主題或同類型股票的相似案例。
- `market_wide`：QQQ100 universe 裡的全市場相似技術型態或市場環境案例。

第一版相似案例使用結構化條件篩選，不使用 LLM 判斷相似案例。

樣本不足時，依序放寬條件：

1. 同產業 / 主題 + 同技術型態 + 同新聞事件類型 + 同市場環境。
2. 同產業 / 主題 + 同技術型態 + 同市場環境。
3. 同技術型態 + 同市場環境。
4. QQQ100 universe 中的同技術型態。

Peer / market evidence quality 第一版規則：

| 條件 | 等級 |
| --- | --- |
| 樣本數 >= 50 且條件相似度高 | `high` |
| 樣本數 20-49 | `medium` |
| 樣本數 5-19 | `low_to_medium` |
| 樣本數 < 5 | `low` |
| 沒資料 | `none` |

如果條件已經放寬太多，即使樣本數很多，也不能給 `high`。

### News Levels

| 欄位 | 規則 |
| --- | --- |
| `sentiment` | 正面關鍵字多於負面為 `positive`；負面多於正面為 `negative`；兩者相同或都沒有為 `neutral`。 |
| `importance` | 財報、財測、訴訟、產業需求主題為 `high`；非中性新聞為 `medium`；一般中性新聞為 `low`。 |

### Stock Research Levels

| 欄位 | 規則 |
| --- | --- |
| `setup_quality` | 綜合分數 >= 4 為 `strong`；>= 1.5 為 `neutral_positive`；<= -1 為 `weak`；其餘為 `neutral`。 |
| `risk_level` | 風險分數 >= 2 為 `high`；>= 1 為 `medium`；低於 1 為 `low`。 |
| `research_confidence` | 同時有新聞與基本面為 `high`；只有其中一種為 `medium`；兩者都沒有為 `low`。 |

### Portfolio Levels

| 欄位 | 規則 |
| --- | --- |
| `position_concentration` | 最大持股 >= 35% 或前三大 >= 75% 為 `high`；最大持股 >= 25% 或前三大 >= 60% 為 `medium`；其餘為 `low`。 |
| `theme_concentration` | 最大主題曝險 >= 50% 為 `high`；>= 35% 為 `medium`；其餘為 `low`。 |
| `portfolio risk_level` | 持股集中度 high、主題集中度 high、或短線轉弱標的 >= 3 檔為 `high`；任一集中度 medium 或有短線轉弱標的為 `medium`；其餘為 `low`。 |

### Market Regime

Market regime 是市場環境分類，不是品質高低：

| 類型 | 意思 |
| --- | --- |
| `bull` | QQQ 或 SPY 在 MA200 上方，且近 3 個月趨勢向上。 |
| `bear` | QQQ 或 SPY 在 MA200 下方，或處於明顯回撤。 |
| `sideways` | 不符合明確 bull / bear 的震盪狀態。 |

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
