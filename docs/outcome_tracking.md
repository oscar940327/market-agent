# Outcome Tracking

這份文件說明 Market Agent 如何讓研究結果被驗證。

我不希望系統只是產生一段看起來合理的分析文字。  
更重要的是：系統要能在未來回頭檢查，當時的判斷後來有沒有站得住腳。

## 想解決的問題

一般直接問 LLM「這檔股票能不能買」時，常見問題是：

- 回答看起來很順，但不一定有資料根據。
- 每次問出來的格式可能不一樣。
- 很難知道它過去回答得準不準。
- 沒有一套機制追蹤後續結果。

Outcome tracking 的目的，就是讓 Market Agent 從「只會回答」變成「可以被驗證」。

當系統產生 ML prediction 或 Research Report 後，它不會只把結果丟掉，而是會在 5 / 10 / 20 個交易日後回頭看實際價格怎麼走，並把結果寫回資料庫。


## 什麼是成熟 Outcome

Outcome 不能在報告產生當天立刻計算。

例如系統在 `2026-07-01` 產生一筆 20 日預測，必須等 20 個交易日後，才知道結果。

這就是「成熟」。

成熟代表：

- 指定的交易日數已經過去。
- Supabase 裡有足夠的後續價格資料。
- 系統可以計算真實報酬、最大下跌、方向是否正確。

如果時間還沒到，狀態會是 `pending`。  
這不是錯誤，只是結果還不能被驗證。

## 為什麼用交易日

Market Agent 使用 trading days，而不是日曆日。

原因很簡單：股票市場不是每天交易。

- 週末不算。
- 美股假日不算。
- 沒有價格資料的日期不能硬算。

所以 5 / 10 / 20 天在這個系統裡，指的是 5 / 10 / 20 個交易日。

## 目前追蹤什麼

目前 outcome tracking 分成兩層。

### 1. ML Prediction Outcomes

這一層追蹤模型每天產生的預測。

它會驗證：

- 5 個交易日後有沒有上漲
- 10 個交易日後有沒有上漲
- 20 個交易日後有沒有上漲
- 20 個交易日內有沒有出現明顯中途下跌
- 預測報酬和實際報酬差多少

這些結果會寫回 Supabase 的 `ml_prediction_outcomes`。

後續的 ML monitoring、metrics、calibration、model health 都會讀這些結果。

### 2. Research Outcomes

這一層追蹤單次研究報告後的實際價格表現。

例如我問：

```text
MU 現在適合進場嗎
```

系統可以把這次研究記錄下來，之後追蹤：

- 5 個交易日後報酬
- 10 個交易日後報酬
- 20 個交易日後報酬
- 期間內最大下跌
- 期間內最大上漲

目前 Step 21 已開始把 Research Outcomes 升級成 research-level tracking。

除了價格結果外，現在也會記錄：

- 當時的 workflow / intent
- 單股或主題成分股 ticker
- 研究結論
- 估值 / 技術 / 新聞狀態
- ML Reference 狀態與信任狀態
- exit signal
- Research Signal 分數
- price plan
- data freshness / evidence quality

主題問題會拆成 constituent ticker 追蹤，例如「記憶體類股」會追蹤 MU、WDC、STX、SNDK 等成功分析的成分股。

Backtest 問題是歷史查詢，不是 forward-looking research signal，所以會記錄 research log，但 outcome 會標記為 `skipped`。

## Outcome 狀態怎麼看

| 狀態 | 展示時可以這樣解釋 |
| --- | --- |
| `pending` | 時間還沒到，結果還不能驗證。 |
| `computed` | 結果已經成熟，並且已經算出來。 |
| `missing_price` | 時間到了，但缺少價格資料，需要檢查資料來源。 |
| `skipped` | 這個 workflow 不適用，不需要計算。 |

最重要的是：`pending` 不是失敗。

如果一筆 20 日 outcome 才過 3 個交易日，它本來就只能是 `pending`。

## 跟 ML Monitoring 的關係

Outcome 是 monitoring 的原料。

Monitoring 的意思是模型健康檢查。  
它會用成熟 outcomes 來檢查：

- 上漲方向準確率
- 大跌風險是否被低估
- 預測機率和真實發生率是否接近
- 報酬估算和實際報酬差多少

如果 outcome 不夠多，模型就沒有足夠資料被評估。  
如果 outcome 累積夠多，系統就能更客觀地判斷 ML Reference 目前該正常顯示，還是應該降低信任。

## 這讓專案多了什麼價值

Outcome tracking 讓 Market Agent 不只是「LLM 包裝過的股票問答」。

它多了一條可驗證的回饋線：

```text
產生研究結果 -> 等待市場結果成熟 -> 寫回資料庫 -> 評估模型與研究流程 -> 改善系統
```

這也是這個專案和一般聊天式回答最大的差別之一。

## 每日測資怎麼累積

目前有一個 daily fixture script，可以一次記錄我每天常測的四個問題：

```bash
python scripts/log_daily_research_fixtures.py
```

預設會記錄：

```text
MU 現在適合進場嗎
記憶體類股現在適合進場觀察嗎
MU 突破策略以前表現怎麼樣
MU 如果我已經持有，現在要不要減碼
```

也可以只記錄指定問題：

```bash
python scripts/log_daily_research_fixtures.py --query "MU 現在適合進場嗎"
```

這個 script 會：

```text
執行研究 workflow
建立 research_logs
建立 research_outcomes
single stock / holding-risk -> pending outcomes
theme -> constituent-level pending outcomes
backtest -> skipped outcomes
```

GitHub Actions 也有一個每日 workflow：

```text
.github/workflows/daily-research-fixtures.yml
```

它會在每天資料更新後：

```text
跑四個固定測資
寫入 Supabase
產生 daily_research_fixture_report_v1.md
寄 email 給我
上傳 artifact
```

之後每日 outcome pipeline 會跑：

```bash
python scripts/compute_research_outcomes.py --limit 100
```

成熟的 outcomes 會被更新成 `computed`。

Daily outcomes workflow 也會產生：

```text
data/research_reports/research_outcome_summary_v1.md
```

這份 summary 會整理已成熟 outcomes，並根據 Step 21.7 的規則判斷當初研究結論後來是偏好、偏差，還是中性。

## 好壞怎麼判斷

Research outcome 的好壞不是看 report 寫得漂不漂亮，而是看成熟後的實際市場結果。

第一版規則大致如下：

- `可列入觀察`、`觀察回踩是否有效`：後續上漲或風險可控，偏好；後續大跌或碰到停損，偏差。
- `暫不進場`、`等待更好價格`：後續下跌或震盪，代表有避開風險；後續大漲，代表可能太保守。
- `reduce` / `exit`：後續下跌或最大跌幅擴大，代表警示有幫助；後續快速上漲，代表可能太保守。
- `backtest`：歷史查詢，不做 forward outcome，標記為 `skipped`。

## 目前限制

目前已經有：

- ML prediction outcome tracking
- Research outcome tracking
- Theme constituent-level outcome tracking
- Backtest skipped tracking
- Price plan touch tracking 欄位

還沒有完整完成：

- Research Signal 分數和後續表現的統計
- exit signal 是否有效的統計
- 各種研究結論的長期表現比較
- 前端顯示 research outcome 成熟狀態
- 長期 research outcome dashboard

daily fixture logging 已經接到 GitHub Actions，第一版會每天產生四題報告、寫入 Supabase，並寄出 email。

## 接下來要補強什麼

Step 21 已完成第一版 Research Signal Outcome Tracking。

它不是只看價格漲跌，而是要驗證整份 Research Report 的判斷。

目前已開始追蹤：

- 當時的 Research Signal 分數
- 當時結論是「可列入觀察」、「暫不進場」還是「等待更好價格」
- 建議進場區間後來有沒有被觸及
- 建議出場區間後來有沒有被觸及
- 止損區間後來有沒有被觸及
- exit signal 是 `hold`、`watch`、`reduce` 還是 `exit`
- 後續 5 / 10 / 20 個交易日表現是否支持當時判斷

後續要做的是把這些結果累積成更長期的 dashboard / 統計頁面，讓我可以看出哪些結論真的比較可靠。

這會讓系統能回答更高層的問題：

- 「可列入觀察」後，後面通常真的有比較好的表現嗎？
- 「暫不進場」是否真的避開短線風險？
- `reduce` 訊號後，股價後續是否真的轉弱？
- Research Signal 分數高低，和後續報酬是否有關？

## Takeaways

- Outcome tracking 是讓系統能被驗證的機制。
- 5 / 10 / 20 天指的是交易日，不是日曆日。
- `pending` 是正常狀態，不是錯誤。
- ML monitoring 需要成熟 outcomes 才能判斷模型健康。
- Research Signal Outcome Tracking 讓整份 Research Report 也能被回測與評估。
