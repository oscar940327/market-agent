# Agentic Research Orchestration

## 這一層解決什麼

原本的 workflow 會依固定順序執行分析。Agentic orchestration 加入一個受控的 LLM Research Orchestrator，讓系統可以根據問題與使用者選取的研究面向，決定要呼叫哪些專業 Agent、需要哪些資料，以及資料不足時是否要補做一次檢查。

它不取代既有計算邏輯。股價、技術指標、基本面、新聞分類、回測與 ML 數字仍由原有資料來源和 Python tools 產生。

## 執行流程

1. Router 判斷研究問題類型。
2. Orchestrator 根據問題與 checkbox 建立 allowlisted execution plan。
3. Technical、Fundamental、News、ML、Theme 等專業 Agent 讀取各自允許的 tools。
4. 每個 Agent 回傳固定 schema，包含 findings、evidence references、confidence、missing data 與 warnings。
5. Risk Agent 讀取已驗證的專業輸出，整理衝突、下跌風險與資料限制。
6. 資料缺口只可觸發白名單內的唯讀補查，並受步數與重規劃上限約束。
7. Report Writer 組成報告；Number Validator 與 Review Agent 再檢查數字和語意。

## 權限邊界

- Agent 只能使用自己 allowlist 內的 tools。
- Tools 在這一版全部為 read-only。
- Agent 不能下單、修改原始 structured data 或直接寫入 Supabase。
- 新聞 Agent 只接收分類後摘要，不把外部原始文字當成系統指令。
- 前端未勾選的研究面向不會交給對應 Agent 或 Report Writer；Risk Agent 仍可執行必要的系統風險檢查。

## Fallback

當 OpenRouter 未設定、LLM 回傳格式錯誤、Tool 失敗或 Agent output 未通過 schema 驗證時，系統會使用既有 deterministic workflow 產生結果。Structured Data 會標示 `fixed_fallback` 與原因。

## Decision Trace

`agentic_orchestration.decision_trace` 會記錄：

- 建立了哪些步驟
- 呼叫了哪些 tools
- 哪些專業 Agent 完成或 fallback
- 是否偵測到觀點衝突或資料缺口
- 是否重新規劃
- Report Writer 與 Review Agent 的處理結果

第一版 trace 只隨 API response 顯示，不寫入 Supabase，避免每天累積大量除錯紀錄。

每日與每週 research fixture Email 會在每個問題前顯示 `Agent Flow: LLM / Fixed / Fallback`。只有 Fallback 時才額外列出原因，不在 Email 增加 token 或模型明細。

## 環境設定

```env
MARKET_AGENT_ORCHESTRATOR_MODE=llm
MARKET_AGENT_ORCHESTRATOR_PROVIDER=openrouter
MARKET_AGENT_ORCHESTRATOR_MODEL=openai/gpt-5.4
MARKET_AGENT_ORCHESTRATOR_MAX_STEPS=8
MARKET_AGENT_ORCHESTRATOR_MAX_REPLANS=2
```

專業 Agent 與 Report Writer 可個別指定模型。目前由 GPT 負責 Orchestrator、專業分析與 Report Writer，Claude Sonnet 負責 Risk Agent 與 Final Reviewer，降低同一模型自我審查的偏誤；完整欄位列在 `.env.example`。

## 目前限制

- Agent 只能在既有資料與 tools 範圍內規劃，不能憑空補出新資料來源。
- Token usage 目前由 OpenRouter client 統一處理，trace 尚未取得逐次 token 成本。
- Agentic orchestration 改善的是研究流程彈性與可追蹤性，不代表 ML 模型準確率因此提高。
