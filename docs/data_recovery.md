# Data Recovery

Data Recovery 讓 `System Data` 不只顯示 `warning`、`stale` 或 `missing`，還能說明問題是否影響本次 Research Report，以及建議怎麼處理。

## Structured Data

單股與主題結果會提供 `data_recovery`：

- `report_impact`：`none`、`usable_with_caution` 或 `insufficient_data`。
- `affects_current_report`：是否影響這次分析。
- `affected_output`：影響技術面、新聞面、基本面、ML Reference 或系統維護。
- `recommended_action`：建議命令與 action id。
- `safe_auto_recovery_candidate`：未來是否適合受控自動重試。
- `automatic_recovery_executed`：第一版固定為 `false`。

第一版是 `advisory_only`：會寫入 Structured Data、pipeline diagnosis、Email 與必要的 GitHub Issue，但不會自行執行命令、修改正式資料或替換模型。

## Report 與維護問題

價格、技術特徵、新聞、基本面或 saved ML prediction 缺失，可能影響本次報告。ML training dataset metadata 或 pipeline run log 過舊，主要是維護問題；只要當次價格、features 與 prediction 可用，不代表報告一定失效。

## 跨環境 Metadata

`weekly-ml-dataset.yml` 建立 dataset 後，會把版本、產生時間、資料截止日、row count 與 GitHub run id 寫入 Supabase 的 `ml_dataset_metadata`。

Freshness 判斷依序使用：

1. Supabase shared metadata。
2. 本地 `training_dataset_v1_metadata.json` fallback。
3. 都不存在時標記 `missing`。

因此 GitHub Actions、Render 與本地不再只依賴各自檔案系統中的 metadata。

## 安全原則

暫時性 provider 錯誤、補算 technical features 或補產生 prediction，未來可以成為受控自動恢復候選。Schema migration、API key、資料刪除、模型 promotion 與 push `main` 必須由使用者確認。
