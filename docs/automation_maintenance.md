# Automation and Self-Maintenance

這份文件說明 Market Agent 如何自動檢查 pipeline、留下診斷、寄送通知，以及把重複問題整理成 GitHub Issue。

## 維護流程

每個 daily、weekly、monthly workflow 完成後，都會執行共用的 maintenance diagnosis：

```text
Workflow 執行
-> 讀取 pipeline log / ML health report
-> rule-based 問題分類
-> 產生 JSON 與 Markdown diagnosis
-> 失敗或 degraded 時建立 / 更新 GitHub Issue
-> 上傳 artifact
```

診斷本身不使用 LLM，也不消耗 OpenRouter token。

## 可以判斷哪些問題

| Category | 意思 | 第一個動作 |
| --- | --- | --- |
| `provider_unavailable` | Provider 暫時失效、rate limit 或 HTTP 5xx | 稍後重試並檢查 provider 限制 |
| `supabase_schema` | Payload 欄位與 Supabase schema 不一致 | 比對 migration 與寫入欄位 |
| `supabase_connection` | Supabase 讀寫或連線失敗 | 檢查服務狀態、secret 與 request |
| `freshness` | 價格、新聞或 pipeline 資料過舊 | 執行對應 pipeline 並檢查依賴日期 |
| `data_recovery` | Structured recovery report 已指出資料缺口 | 使用報告中的指定命令，確認後再執行 |
| `ml_health` | 模型品質、校準或 drift 警告 | 維持 reduced trust 並查看 monitoring artifact |
| `configuration` | Secret、權限或環境設定錯誤 | 檢查 GitHub Secrets 與 workflow permissions |
| `test_failure` | pytest 或維護檢查失敗 | 本地重現後在獨立分支修正 |
| `unknown` | 固定規則無法判斷 | 人工查看完整 log |

## GitHub Issue 如何運作

以下狀態會建立或更新 Issue：

- `failed`
- `partial_success`
- `degraded`
- `stale`
- `missing`

系統會用 pipeline、問題分類與失敗 step 產生 fingerprint。
同一個 fingerprint 再次發生時，不會每天建立新 Issue，而是在原 Issue 留下新的 occurrence comment。

單純 `warning` 仍會留在 diagnosis artifact，但不會自動建立 Issue，避免 Issue 數量失控。

Data Recovery 第一版也會透過現有 pipeline alert 寄 Email。通知包含缺口、是否影響 Research Report 與 recommended action，但不會在背景自行執行修復命令。

每月 model promotion workflow 不論候選模型是否通過都會寄出 Email，明確寫出「不建議更換」、「繼續觀察」或「建議更換」。建議更換仍需使用者確認，自動化沒有權限直接替換 production model。

## Diagnosis Artifact

每次 workflow 都會保留：

```text
data/maintenance/diagnoses/<pipeline>_<timestamp>.json
data/maintenance/diagnoses/<pipeline>_<timestamp>.md
data/maintenance/diagnoses/<pipeline>_latest.json
data/maintenance/diagnoses/<pipeline>_latest.md
```

這些檔案只存在該次 GitHub Actions artifact，不會由排程直接 commit 回 repository。

## Issue 到 PR 的安全流程

自動化可以協助：

1. 根據 Issue 與 artifact 分析問題。
2. 建立獨立修正分支。
3. 修改程式與文件。
4. 執行 pytest 與 documentation sync check。
5. 建立 Pull Request。

自動化不能：

- 直接 push 到 `main`。
- 自動合併未審查的 PR。
- 在 log、Issue 或 PR 顯示 secret。
- 在沒有 migration review 的情況下修改正式 Supabase schema。

PR 必須由使用者確認後才合併。

## 文件同步檢查

`maintenance-checks.yml` 會在 Pull Request 執行完整測試與文件同步檢查：

- Workflow、alerts、maintenance code 改變時，需要同步更新本文件、Data Pipeline 或 README。
- `.env.example` 改變時，需要同步更新 Deployment 或 README。
- Supabase migration 改變時，需要同步更新 Supabase Schema 文件。

## 本地測試

建立診斷但不建立 Issue：

```bash
python scripts/build_pipeline_diagnosis.py --pipeline local-test --status failed --message "HTTP Error 503"
```

預覽 Issue 同步：

```bash
python scripts/sync_github_issue.py --diagnosis data/maintenance/diagnoses/local-test_latest.json --dry-run
```

檢查指定檔案是否需要同步文件：

```bash
python scripts/check_documentation_sync.py --path .github/workflows/daily-prices.yml --path docs/automation_maintenance.md
```
