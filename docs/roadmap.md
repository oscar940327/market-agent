# Roadmap

這份文件說明 Market Agent 接下來的發展方向。

它不是單純 TODO list，而是用來展示：這個專案目前做到哪裡，以及接下來會怎麼演進。

## 目前狀態

Market Agent 目前已經完成一個可以 demo 的研究系統。

已完成的核心能力：

- 自然語言 research question routing
- 單股研究報告
- 主題 / 產業掃描
- 策略回測
- 持有風險與出場觀察
- ML Reference
- Supabase 資料儲存
- GitHub Actions 自動化
- Render 後端部署
- System Data / Evidence / ML Reference 狀態顯示

目前定位是 research assistant，不是自動交易系統。

## 短期方向

### 1. 文件與展示

目標是讓專案能被清楚展示。

重點：

- README 作為總覽。
- docs 拆成短文件。
- 每份文件都能支援 demo 講解。
- 說清楚技術設計、資料流程、ML 限制與未來方向。

### 2. Research Signal Outcome Tracking

目前已經有 ML prediction outcomes 和基礎版 research outcomes。

下一步是追蹤整份 Research Report 的後續表現。

會補強：

- Research Signal 分數和後續報酬的關係
- 結論是否和後續結果一致
- 價格計畫是否命中
- exit signal 是否有效
- 不同 conclusion 的長期表現

這會讓系統能回答：

```text
這套研究流程過去真的有用嗎？
```

### 3. 自動化維護流程

目前 GitHub Actions 已經能更新資料並寄錯誤信。

未來希望補強：

- 更清楚的 pipeline diagnosis report
- 自動建立可追蹤 issue
- AI 協作修正流程
- 文件更新規則
- 不能無監督直接 push 到 main

目標不是完全自動亂改，而是建立可控的自我維護流程。

## 中期方向

### 4. Model Retraining and Promotion Automation

Step 28 已具備可重現的模型選拔機制，但目前仍需手動啟動。下一階段會使用 GitHub Actions 每月或每季重跑比較，產生版本化報告並寄送 Email。

通過政策的 candidate 會先進入 shadow validation：舊模型繼續服務，candidate 只同步產生預測並等待真實 outcomes 驗證。系統不會因單次測試自動替換 production model，也不會直接 push 到 main。

### 5. Portfolio Workflow Refactor

Portfolio 目前不是主要展示重點。

未來會獨立大改：

- 持股輸入
- 權重與集中度
- theme exposure
- portfolio-level risk
- 個股風險對整體 portfolio 的影響
- portfolio report layout

這會讓系統從「單一股票研究」往「個人投資組合研究」延伸。

### 6. Frontend Redesign / Monitoring UI

目前前端已可 demo，但未來如果要展示更多 health / monitoring 資訊，需要重新整理畫面層級。

可能方向：

- Data Health dashboard
- ML Health dashboard
- Outcome history
- Research Signal track record
- Structured Data 摘要化
- single stock / theme / portfolio 不同版面

## 長期方向

### 7. Better ML Models

目前 ML Reference 是 research-only。

Step 28 已完成第一輪 walk-forward 多模型比較與 promotion policy。結果只有 `large_drop_20d` 候選達到 `medium` 並通過單一 target policy；目前已支援 target-level shadow validation，因此它可以獨立累積真實 outcomes。Production model 不會自動被替換，ML Reference 在人工確認前仍維持 `reduced_trust`。

長期可以改善：

- 更完整的 features
- 更穩定的 labels
- 更好的 downside risk modeling
- calibration 改善
- 讓已通過的 downside candidate 先進行 target-level shadow validation（已完成）
- 針對未通過的 upside / return targets 改善 features 與 labels
- 持續比較 XGBoost / LightGBM candidates
- quantile regression / return range model
- 更完整的 model promotion policy

模型升級不會只看準確率，也會看風險、校準、穩定性與可解釋性。

### 8. News and Sentiment Improvement

新聞目前已能收集、分類、摘要，但仍有改善空間。

未來方向：

- 更好的新聞來源
- 去重與事件合併
- source quality
- ticker relevance
- 事件重要性
- 新聞對短線情緒和基本面預期的區分

社群資料目前因 API 取得不易，暫不作為近期主線。

### 9. Agent Structure Refactor

目前已經是 controlled agent workflow，但不是每個 agent 都獨立成大型資料夾。

未來可以更清楚切分：

- Market Data Agent
- Technical Agent
- Fundamental Agent
- News Agent
- ML Research Agent
- Evidence Agent
- Report Agent
- Orchestrator

目標是讓系統更好維護，而不是為了形式硬拆。

## 不做什麼

目前不打算做：

- 自動下單
- 交易執行
- 保證收益
- 完全無人監督自動改 main branch
- 把 LLM 當成唯一決策來源

這些限制是刻意設計，不是功能缺失。

## Takeaways

- 現在版本已經能展示完整 research workflow。
- 下一個關鍵是讓 Research Signal 也能被 outcome 驗證。
- Portfolio 和前端大改會延後，等 single stock / theme / ML Reference 更穩定後再做。
- 長期方向是更可信、更可追蹤、更能自我改善的投資研究系統。
