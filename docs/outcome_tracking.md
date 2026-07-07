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

目前這是基礎版，已經可以追蹤價格結果。

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

## 目前限制

目前已經有：

- ML prediction outcome tracking
- 基礎版 research outcome tracking

還沒有完整完成：

- Research Signal 分數和後續表現的統計
- 價格計畫是否命中的追蹤
- exit signal 是否有效的統計
- 各種研究結論的長期表現比較

這些會在後續 `Research Signal Outcome Tracking` 裡補強。

## 接下來要補強什麼

下一階段是 `Research Signal Outcome Tracking`。

它不是只看價格漲跌，而是要驗證整份 Research Report 的判斷。

未來會追蹤：

- 當時的 Research Signal 分數
- 當時結論是「可列入觀察」、「暫不進場」還是「等待更好價格」
- 建議進場區間後來有沒有被觸及
- 建議出場區間後來有沒有被觸及
- 止損區間後來有沒有被觸及
- exit signal 是 `hold`、`watch`、`reduce` 還是 `exit`
- 後續 5 / 10 / 20 個交易日表現是否支持當時判斷

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
- 未來 Research Signal Outcome Tracking 會讓整份 Research Report 也能被回測與評估。
