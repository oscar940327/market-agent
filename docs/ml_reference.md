# ML Reference

這份文件說明 Market Agent 裡的 `ML Reference` 是什麼、它如何產生、哪些狀態代表什麼，以及為什麼它目前只作為研究輔助訊號。

## 定位

ML Reference 是機器學習參考訊號。

它不是：

- 自動交易模型
- 直接買賣建議
- 會單獨決定 Research Report 結論的模型

它的用途是提供額外參考：

- 5 / 10 / 20 個交易日後上漲機率
- 20 個交易日內中途大跌風險
- 歷史相似情境報酬區間
- 實驗版報酬模型估算

目前 Research Report 會把 ML Reference 寫進報告，但不讓它直接覆蓋基本面、技術面、新聞面與價格計畫。

## 為什麼不直接讓 ML 決定結論

金融市場資料很吵，短期價格受很多因素影響。

目前模型仍有幾個限制：

- 20 日上漲預測表現不穩。
- 20 日中途大跌風險容易低估或需要保守解讀。
- 報酬模型仍是第一版實驗模型。
- 新聞與 similar-case 特徵仍在累積中。
- 模型還沒有達到 promote 成正式模型的標準。

所以 ML Reference 目前是 reference-only。

## ML Reference 會顯示什麼

### 上漲與風險機率

| 欄位 | 意思 |
| --- | --- |
| `up_5d` | 5 個交易日後收盤價高於目前價格的機率。 |
| `up_10d` | 10 個交易日後收盤價高於目前價格的機率。 |
| `up_20d` | 20 個交易日後收盤價高於目前價格的機率。 |
| `large_drop_20d` | 未來 20 個交易日內出現明顯中途下跌的風險。 |

這些數字是參考機率，不是保證。

### 歷史相似情境參考

這一段不是模型直接預測，而是從歷史資料中找相似條件，整理過去報酬區間。

常見欄位：

| 欄位 | 意思 |
| --- | --- |
| `sample_size` | 相似樣本數。 |
| `evidence_quality` | 歷史樣本證據品質。 |
| `expected_return_range_5d` | 過去相似情境 5 日報酬區間。 |
| `expected_return_range_10d` | 過去相似情境 10 日報酬區間。 |
| `expected_return_range_20d` | 過去相似情境 20 日報酬區間。 |
| `max_drop_range_20d` | 過去相似情境 20 日內中途最大跌幅區間。 |

目前這段通常比報酬模型更適合當主要參考。

### 報酬模型估算

報酬模型會估算：

- 5 日報酬
- 10 日報酬
- 20 日報酬
- 20 日內中途最大跌幅

這是第一版實驗模型。  
如果 model quality 是 `low` 或 `low_to_medium`，Research Report 會提醒要保守解讀。

## ML Reference 來源狀態

前端的 `ML Reference` badge 會顯示來源與可用狀態。

| 狀態 | 意思 |
| --- | --- |
| `saved / fresh` | 使用 Supabase 中已儲存、可用的每日 prediction。 |
| `saved / warning` | 使用 Supabase prediction，但 freshness 有提醒。 |
| `aggregated / fresh` | Theme workflow 使用多檔成分股 saved prediction 聚合。 |
| `fallback` | 找不到可用 saved prediction，改用 runtime fallback。 |
| `not used` | 這個 workflow 不使用 ML Reference，例如策略回測。 |
| `unavailable` | ML Reference 無法產生，本次不應作為判斷依據。 |

## saved prediction 與 runtime fallback

### saved prediction

正式情境優先使用 saved prediction。

流程是：

1. GitHub Actions 執行 `daily-ml-predictions.yml`。
2. 系統讀取 Supabase 的最新價格、技術特徵、新聞摘要與基本面狀態。
3. 產生每日 ML prediction。
4. 寫入 `ml_predictions`。
5. 使用者查詢時，Render 後端優先讀 `ml_predictions`。

這是比較穩定的路徑。

### runtime fallback

如果 saved prediction 不可用，系統會嘗試 runtime fallback。

常見原因：

- 還沒有跑過 `daily-ml-predictions`。
- saved prediction status 不是 `ready`。
- saved prediction freshness 是 `missing` 或不可用。
- Supabase 暫時讀不到資料。

fallback 不是一定錯，但正式 demo 時最好避免長期依賴 fallback。

## Theme ML Reference

Theme workflow 不是直接訓練一個主題模型。

目前做法是：

1. 找出主題內成分股。
2. 讀取每檔股票的 saved daily prediction。
3. 聚合成主題層級 ML Reference。

例如記憶體主題會聚合 MU、WDC、STX、SNDK 等成分股。

Theme ML Reference 會顯示：

- 覆蓋幾檔成分股
- 平均 5 / 10 / 20 日上漲機率
- 平均 20 日大跌風險
- 主題內訊號分布

這仍然是 reference-only。

## Backtest 為什麼顯示 not used

策略回測問題主要回答：

- 這個策略以前表現怎麼樣
- 勝率多少
- 平均報酬多少
- 最大虧損多少
- 歷史資料範圍多久

這類問題不需要 ML Reference。  
所以前端顯示 `ML Reference: not used` 是正常狀態。

## 降低信任狀態

Research Report 可能會出現：

```text
ML Reference 目前為降低信任狀態，相關數字應保守解讀。
```

這不是說 ML Reference 完全不能看。

它的意思是：ML 可以提供參考，但目前不應把它看成高可信度訊號。

常見原因：

- 20 日上漲 signal quality 是 `low` 或 `unknown`。
- 20 日大跌風險 signal quality 不夠高。
- 報酬模型品質是 `low`、`low_to_medium` 或 `unknown`。
- saved prediction freshness 是 `warning`。
- ML health report 顯示 model quality、calibration 或 drift 有問題。

## ML Health

ML Health 是系統用來檢查模型狀態的監控報告。

主要檢查：

| 項目 | 意思 |
| --- | --- |
| `model_quality` | 近期 prediction outcome 的整體表現。 |
| `calibration` | 預測機率和真實發生率是否接近。 |
| `drift` | 最新資料分布是否和過去訓練資料差太多。 |
| `model_upgrade` | 是否有候選模型值得升級。 |

如果 ML Health 是 `degraded`，ML Reference policy 通常會是 `reduced_trust`。

## Monitoring 門檻

Monitoring 門檻的意思就是：系統用哪些標準判斷 ML Reference 現在能不能信。

目前主要門檻：

| 指標 | 門檻 |
| --- | --- |
| 最小樣本數 | `50` |
| 上漲方向準確率 | 至少 `50%` |
| downside underestimation rate | 不應高於 `20%` |
| mean absolute calibration error | 不應高於 `10%` |
| max calibration error | 不應高於 `20%` |

這些門檻不是投資標準答案，而是目前系統用來判斷模型是否需要保守看待的工程規則。

## Model Promotion Policy

目前候選模型不會自動取代正式模型。

升級模型前需要：

1. 有足夠成熟 outcomes。
2. 指標比 baseline 更好。
3. calibration 沒有明顯惡化。
4. downside / max-drop 風險沒有更差。
5. drift 沒有明顯 warning。
6. 人工確認後才 promote。

系統可以自動提出 model upgrade review，但不會無監督直接替換正式模型。

##  prediction 

目前系統每天會做：

- 更新資料
- 產生新的 daily prediction
- 寫入 Supabase
- 等未來 5 / 10 / 20 個交易日成熟後驗證

但這不代表每天重新訓練模型。

模型訓練應該在：

- feature 有重大改動
- outcomes 累積到足夠數量
- monitoring 顯示模型長期退化
- 有候選模型需要比較

每天重訓會讓版本混亂，也不一定讓模型更好。

## 前端怎麼解讀

前端通常會同時看到：

| Badge | 意思 |
| --- | --- |
| `Evidence` | 本次研究資料與訊號證據品質。 |
| `System Data` | 價格、技術、新聞、pipeline 資料是否新鮮。 |
| `ML Reference` | ML Reference 來源與可用狀態。 |

其中 `ML Reference` 只回答：這次 ML 參考訊號能不能看、從哪裡來、信任度如何。

它不等於整份 Research Report 的證據品質。

## 目前限制

- ML Reference 還不是 production-grade investment model。
- Theme ML Reference 是成分股 prediction 聚合，不是主題專用模型。
- 報酬模型仍是 experimental reference。
- 新聞與 similar-case feature 仍需要持續累積。
- Portfolio workflow 尚未重新設計。
