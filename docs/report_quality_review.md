# Research Report 品質審查

這份文件說明 Market Agent 如何檢查 Research Report 的產出品質。這套審查不判斷股票後來是否真的上漲；5 / 10 / 20 個交易日後的正確性仍由 outcome tracking 驗證。

## 兩層審查

第一層是 deterministic review，檢查必要段落、Structured Data 重要數字、ML trust、資料 freshness、持有問題格式、風險聲明與明顯過度自信語句。

重要數字包含基本面 ratio 轉換後的百分比、MA20、MA50、MACD histogram 與 ML 機率。LLM 修訂若誤改基本面百分比，系統會先依 Structured Data 自動恢復，再重新審查；缺漏或仍不一致時則不予通過。

第二層是 semantic review，由 OpenRouter 的 `openai/gpt-5.4-mini` 檢查報告是否真的回答問題，且沒有扭曲 Structured Data。

## 品質分數

| 維度 | 檢查內容 |
| --- | --- |
| `query_relevance` | 是否直接回答使用者原始問題。 |
| `evidence_consistency` | 文字、數字與結論是否符合 Structured Data。 |
| `risk_balance` | 是否同時交代支持與反對訊號、限制與重大風險。 |
| `clarity` | 是否清楚、可讀且沒有不必要重複。 |
| `hallucination_safety` | 是否避免加入資料中不存在的事件、數字或原因。 |
| `overall_quality` | 整體是否可作為研究摘要閱讀。 |

每個維度為 1～5 分，全部至少 4 分才可通過。即使 LLM 回傳 `pass`，只要任一分數低於 4，程式仍會強制改成 `needs_revision`。

## 修訂流程

```text
產生 Research Report
  -> deterministic review
  -> semantic review
  -> 未通過時依 findings 修訂
  -> 重新執行兩層審查
  -> 最多修訂 2 次
```

每次修訂後都必須重新檢查。兩次後仍未通過時，系統保留最後一版報告與未解決問題，不會假裝品質合格。

## 品質層級不混用

- `evidence_quality.level`：整份研究資料的整體證據品質。
- `return_reference.evidence_quality`：只評估歷史相似情境這個子項的樣本品質。
- `ml_reference_trust`：決定 ML 數字應正常使用或降低信任。

因此「歷史相似情境子項為 high、整體證據為 medium、ML Reference 為降低信任」可以同時成立。Semantic reviewer 不應將三者誤判為矛盾。

資料新鮮度也只影響被標記的來源。例如 ML training data 過舊會降低 ML Reference 信任度，但不代表最新價格、技術面與基本面全部失效。

## 使用範圍

- 每日與每週固定 fixture：使用 `semantic`，每份報告都執行 LLM 品質審查。
- 一般前端查詢：維持 `hybrid`，deterministic review 通過時不額外呼叫 reviewer，以控制延遲與 token 成本。
- `deterministic`：完全不使用 reviewer LLM。

## 紀錄與通知

品質結果寫入 `report_review`，內容包含：

- 最終狀態
- 六個品質分數
- reviewer provider / model
- 修訂次數
- findings 與未解決問題
- iteration history

每日與每週研究 Email 會顯示每份報告的品質摘要及整體平均分數。任何 fixture 未通過時，script 會以失敗狀態結束，Step 26 diagnosis 會建立或更新對應 GitHub Issue。

## 環境設定

```env
MARKET_AGENT_REPORT_REVIEW_MODE=hybrid
MARKET_AGENT_REPORT_REVIEW_PROVIDER=openrouter
MARKET_AGENT_REPORT_REVIEW_MODEL=openai/gpt-5.4-mini
MARKET_AGENT_REPORT_REVIEW_MAX_ITERATIONS=2
```

GitHub Actions 的 daily fixture 使用 `hybrid`，weekly fixture 使用 `semantic`；兩者都使用最多兩次修訂的成本控制策略。
