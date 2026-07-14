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

### 模型品質是什麼

這裡的 `model_quality` 是報酬模型在未參與訓練的 test data 上，預測誤差有多大的簡化標籤。它不是 Evidence Quality、資料新鮮度、LLM 報告品質或整體 ML Health。

目前第一版只使用 test MAE 分級。MAE 代表模型預測報酬與真實報酬平均相差多少個百分點：

#### MAE 怎麼計算

MAE 是 Mean Absolute Error，中文是「平均絕對誤差」。計算方式是：

```text
MAE = 所有樣本的 |模型預測值 - 真實結果| 加總 ÷ 樣本數
```

公式可寫成：

```text
MAE = (1 / n) × Σ |prediction_i - actual_i|
```

系統會先用沒有參與模型訓練的 test data 產生預測，再將每筆預測和後來真正發生的 outcome 比較。程式內的報酬使用小數儲存，因此：

- `0.01` 代表 1%。
- `0.037` 代表平均相差約 3.7 個百分點。
- MAE 不保留正負方向；高估 5% 和低估 5% 都算 5% 誤差。

簡化範例：

| 樣本 | 模型預測報酬 | 真實報酬 | 絕對誤差 |
| --- | ---: | ---: | ---: |
| A | +5% | +2% | 3% |
| B | -2% | -6% | 4% |
| C | +3% | +5% | 2% |

```text
MAE = (3% + 4% + 2%) ÷ 3 = 3%
```

各 target 的比較方式如下：

| Target | prediction | actual outcome |
| --- | --- | --- |
| `forward_return_5d` | 模型估算的 5 個交易日報酬 | 5 個交易日後實際收盤報酬 |
| `forward_return_10d` | 模型估算的 10 個交易日報酬 | 10 個交易日後實際收盤報酬 |
| `forward_return_20d` | 模型估算的 20 個交易日報酬 | 20 個交易日後實際收盤報酬 |
| `max_drop_20d` | 模型估算的 20 日內最大跌幅 | 接下來 20 個交易日的每日收盤價中，相對目前收盤價出現的最大跌幅 |

例如模型預測 20 日報酬為 `+10%`，最後實際報酬為 `+2%`，這筆樣本的絕對誤差就是 8 個百分點。若模型預測最大跌幅為 `-5%`，實際曾跌到 `-12%`，絕對誤差是 7 個百分點；同時這也屬於低估下跌風險，所以還需要另外檢查 downside underestimation rate。

MAE 的優點是直覺且不會讓正負誤差互相抵銷，但它也有侷限：它不會告訴我們模型是否看對漲跌方向、不會單獨反映風險低估，也不會判斷預測區間是否合理。因此 Step 28 不能只靠 MAE 評定完整模型品質。

| 現行標籤 | 現行程式規則 | 目前應如何理解 |
| --- | --- | --- |
| `medium` | MAE ≤ 3.5% | 平均誤差相對較小，但仍只適合作為研究參考。 |
| `low_to_medium` | 3.5% < MAE ≤ 5.5% | 有部分參考性，但單點預測的誤差仍明顯，應搭配歷史區間。 |
| `low` | MAE > 5.5% | 平均誤差過大，不應依賴精確報酬數字。 |
| `unknown` | 找不到 test MAE | 缺少 metrics，無法判斷模型品質。 |
| `high` | 第一版尚未定義 | 現行程式不會產生 `high`。 |

因此，「模型品質低」不代表這次預測一定錯，而是模型在過去未見資料上的平均誤差太大，尚不足以把預測的 `+X%` 當成可靠價格目標。

目前基準模型的 test MAE 約為：

| Target | Test MAE | 現行模型品質 |
| --- | ---: | --- |
| 5 日報酬 | 3.7% | `low_to_medium` |
| 10 日報酬 | 5.4% | `low_to_medium` |
| 20 日報酬 | 7.9% | `low` |
| 20 日內最大跌幅 | 4.5% | `low_to_medium` |

這個第一版規則也有明顯限制：它只看 MAE、所有預測天數共用同一門檻，而且沒有 `high`。Step 28 會改成多指標政策，加入 walk-forward 時間外測試、相對基準改善、方向準確率、校準、預測區間覆蓋、downside underestimation 與不同市場環境的穩定性。

升級後的品質語意預計為：

| 目標標籤 | 完整語意 |
| --- | --- |
| `high` | 在多個 walk-forward 時段與主要市場環境穩定勝過 naive baseline，方向、校準、區間與 downside 指標都通過 promotion policy。 |
| `medium` | 有可重複的時間外效果，主要風險指標通過，可作為有條件的研究參考。 |
| `low_to_medium` | 有局部效果，但誤差、穩定性、校準或風險估計仍有限。 |
| `low` | 未穩定勝過基準、誤差過大或低估風險，不應依賴單點預測。 |
| `unknown` | 缺少足夠資料、outcomes 或 metrics，無法評級。 |

### 保守風險修正

Downside overlay 會在使用者查詢時重新使用本次最新技術資料，包括價格相對 MA20、MACD histogram、20 日波動與當前技術訊號。市場環境仍沿用 saved prediction 的市場 context。

Research Report 會標示 overlay 技術資料的 `data_as_of`。這可避免 saved prediction 的舊技術 snapshot 與報告最新技術面互相矛盾；如果最新技術面已改善，先前套用的保守跌幅也能被撤銷並重新計算。

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

## ML 信任說明

Research Report 會在 ML Reference 後面顯示精簡的信任說明：

```text
ML 信任說明:
- 信任狀態：降低信任。
- 狀態說明：本次 ML Reference 為降低信任，主要受到模型品質、校準或風險估計限制。
- 主要原因：版本化模型政策記錄校準仍有待改善；20 日上漲方向的訊號品質偏低。
- 支持證據：prediction freshness 為 fresh；歷史相似情境樣本充足。
- 使用方式：保留數字作風險與情境參考，但不可單獨改變結論、價格計畫或出場決策。
```

目前支援五種說明狀態：

| 狀態 | 解讀方式 |
| --- | --- |
| `normal` | 沒有觸發信任降級，可作為輔助參考。 |
| `reduced_trust` | 可以看，但模型品質、校準或風險估計仍有限。 |
| `fallback` | 使用 runtime fallback，穩定性低於 saved prediction。 |
| `unavailable` | 沒有可用 ML Reference，本次應忽略 ML 數字。 |
| `skipped` | 這個 workflow 不使用 ML，例如回測查詢。 |

Structured Data 的 `ml_trust_explanation` 會保留完整內容：

- `reason_codes`
- 完整 `reasons`
- `supports`
- `affected_outputs`
- prediction 來源、freshness、model version
- 版本化 model policy 來源

目前版本化政策讀取 `step20_improvement_summary_v1.json`。它記錄 baseline_v1 維持 `reduced_trust`、calibration 尚待改善、candidate v2 尚未 promote，以及 downside overlay 仍需保留。

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
