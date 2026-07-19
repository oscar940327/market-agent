# Model Promotion

這份文件說明候選模型如何被定期比較、進入 shadow validation，以及什麼情況下系統才會建議更換正式模型。

## 每月流程

`monthly-model-promotion.yml` 於每月 2 日台灣時間 15:00 執行：

```text
更新 training dataset
-> 執行 Step 28 walk-forward 比較
-> 檢查既有 shadow outcomes
-> 產生明確 recommendation
-> 寫入 Supabase
-> 寄送 Email
```

Email 一定會明確顯示以下其中一種結論：

- `no_candidate`：本月沒有可驗證的候選模型。
- `keep_production`：不建議更換正式模型。
- `start_shadow`：建議候選模型進入並行觀察。
- `continue_shadow`：資料仍不足，繼續並行觀察。
- `promote_candidate`：建議更換正式模型，但仍需使用者確認。
- `unable_to_decide`：資料或流程不足，暫時無法判斷。

## Shadow Validation

候選模型通過 Step 28 後，系統會建立一批 QQQ100 shadow predictions，使用 `prediction_role=shadow` 寫入 `ml_predictions`。Promotion 以 target 為單位：例如只有 `large_drop_20d` 通過時，可以只觀察這個風險模型，不需要等待 `up_5d`、`up_10d`、`up_20d` 一起通過。

Shadow prediction：

- 不會顯示在 Research Report。
- 不會改變 ML Reference 或最後結論。
- 會由現有 outcome workflow 計算該 target 成熟後的真實結果。
- 至少觀察 45 天，且每個候選 target 至少累積 100 筆 outcomes，才進入正式比較。
- 分類時使用的 decision threshold 會跟 prediction 一起保存，outcome 不會一律錯用 `0.5` 判斷。

正式查詢只讀取 `prediction_role=production`，因此 shadow 資料不會意外取代 production output。

## 升級條件

系統會比較 production 與 shadow 的：

- 5／10／20 日上漲方向準確率。
- Brier score，也就是機率預測是否校準。
- 20 日大跌事件 recall 與 Brier score，避免漏掉重要下跌風險，也避免機率品質惡化。
- 樣本數與觀察時間。

即使結果為 `promote_candidate`，`automatic_replacement` 仍固定為 `false`。系統只會 Email 建議更換，不會自行替換 model artifact、修改正式版本或解除 `reduced_trust`。

## Supabase

Step 30 使用：

- `ml_predictions.prediction_role`
- `ml_model_registry`
- `ml_promotion_reviews`

啟用前需執行 `supabase/migrations/015_create_model_promotion_tables.sql`。
