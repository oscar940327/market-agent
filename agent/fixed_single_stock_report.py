from agent.report_context import build_single_stock_report_context


def build_fixed_single_stock_report(data: dict) -> str:
    context = build_single_stock_report_context(data)
    sections = [
        ("研究摘要", build_research_summary(context)),
        ("基本面分析", build_fundamental_analysis(context)),
        ("技術面分析", build_technical_analysis(context)),
        ("新聞面分析", build_news_analysis(context)),
        ("ML Reference", build_ml_reference(context)),
    ]

    if context.get("question_type") == "holding_exit":
        sections.append(("持有風險 / 出場觀察", build_exit_signal_analysis(context)))

    sections.extend(
        [
            ("綜合評估", build_overall_assessment(context)),
            ("風險提醒", build_risk_reminder(context)),
        ]
    )
    return "\n\n".join(f"{title}\n{body}" for title, body in sections)


def build_research_summary(context: dict) -> str:
    ticker = context.get("ticker") or "這檔股票"
    decision = build_decision(context)
    profile = context.get("research_profile") or {}
    evidence_quality = context.get("evidence_quality") or {}
    confidence = profile.get("research_confidence", "unknown")
    evidence_level = evidence_quality.get("level", confidence)
    return (
        f"{ticker}目前結論為「{decision['conclusion']}」。"
        f"估值判斷是「{decision['valuation']}」，"
        f"技術面是「{decision['technical']}」，"
        f"研究信心為 {confidence}，證據品質為 {evidence_level}。"
    )


def build_fundamental_analysis(context: dict) -> str:
    fundamentals = context.get("fundamentals") or {}
    valuation = get_valuation_label(fundamentals)
    status = fundamentals.get("status")
    if status == "skipped":
        return "這次未納入基本面資料，因此估值判斷需要另外搭配財報、成長率、獲利能力與同業比較再確認。"
    if status and status != "success":
        return "目前基本面資料不足，暫時無法可靠判斷估值高低，建議先補齊營收成長、獲利能力與本益比資料。"

    metrics = fundamentals.get("metrics") or {}
    parts = [f"目前估值判斷為「{valuation}」。"]
    forward_pe = to_float(metrics.get("forward_pe"))
    trailing_pe = to_float(metrics.get("trailing_pe"))
    revenue_growth = to_float(metrics.get("revenue_growth"))
    earnings_growth = to_float(metrics.get("earnings_growth"))
    gross_margins = to_float(metrics.get("gross_margins"))

    if forward_pe is not None:
        parts.append(f"Forward P/E 約 {forward_pe:.1f}。")
    elif trailing_pe is not None:
        parts.append(f"Trailing P/E 約 {trailing_pe:.1f}。")
    if revenue_growth is not None:
        parts.append(f"營收成長約 {revenue_growth * 100:.1f}% 。")
    if earnings_growth is not None:
        parts.append(f"獲利成長約 {earnings_growth * 100:.1f}% 。")
    if gross_margins is not None:
        parts.append(f"毛利率約 {gross_margins * 100:.1f}% 。")

    risks = (fundamentals.get("summary") or {}).get("risks") or []
    if risks:
        parts.append("仍需留意估值、負債或獲利波動帶來的風險。")
    if fundamentals.get("provider") == "static_fallback":
        parts.append("基本面資料使用部署環境 fallback，之後仍應以最新 provider 或 Supabase 資料更新。")

    return " ".join(parts)


def build_technical_analysis(context: dict) -> str:
    technical = context.get("technical_analysis") or {}
    signals = context.get("signals") or {}
    label = get_technical_label(context)
    parts = [f"目前技術判斷為「{label}」。"]

    current_price = to_float(technical.get("current_price"))
    ma20 = to_float(technical.get("ma20"))
    ma50 = to_float(technical.get("ma50"))
    rsi14 = to_float(technical.get("rsi14") or technical.get("rsi_14"))
    macd = to_float(technical.get("macd"))
    macd_signal = to_float(technical.get("macd_signal"))
    macd_histogram = to_float(technical.get("macd_histogram"))

    if current_price is not None:
        parts.append(f"股價約 {format_money(current_price)}。")
    if ma20 is not None:
        parts.append(f"MA20 約 {format_money(ma20)}。")
    if ma50 is not None:
        parts.append(f"MA50 約 {format_money(ma50)}。")
    if rsi14 is not None:
        parts.append(f"RSI 14 為 {rsi14:.1f}，{describe_rsi(rsi14)}")
    if macd is not None and macd_signal is not None and macd_histogram is not None:
        parts.append(
            f"MACD 為 {macd:.4f}，signal 為 {macd_signal:.4f}，histogram 為 {macd_histogram:.4f}。"
        )

    parts.append(describe_momentum_state(technical.get("momentum_state", "neutral")))

    if (signals.get("breakout") or {}).get("is_breakout"):
        parts.append("價格有突破訊號，但仍需確認是否能延續。")
    if (signals.get("volume_surge") or {}).get("is_volume_surge"):
        parts.append("成交量有放大，短線關注度提高。")
    if (signals.get("pullback") or {}).get("is_pullback"):
        parts.append("價格接近 MA20 回踩區，可觀察支撐是否有效。")
    if technical.get("short_term_trend") == "weak" or technical.get("is_above_ma20") is False:
        parts.append("若尚未站回關鍵均線，立即進場信心較低。")

    parts.append(build_historical_signal_text(context.get("backtest_evidence") or {}))
    return " ".join(parts)


def build_news_analysis(context: dict) -> str:
    summary = context.get("news_summary") or {}
    total_items = int(summary.get("total_items") or 0)
    if not total_items:
        return "這次沒有納入新聞資料，判斷主要來自技術面與基本面資料。"

    sentiment = summary.get("sentiment") or "neutral"
    high_importance_count = int(summary.get("high_importance_count") or 0)
    impact_type = get_news_impact_type(summary.get("top_topics") or {}, sentiment)
    impact_level = "高" if high_importance_count >= 2 else "中" if high_importance_count == 1 or sentiment != "neutral" else "低"
    sentiment_label = {"positive": "偏利多", "negative": "偏利空"}.get(sentiment, "中立")
    explanation = describe_news_impact_type(impact_type)

    if sentiment == "negative":
        ending = "如果技術面仍未轉強，新聞面會降低立即進場的信心，較適合等待價格與量能重新確認。"
    elif sentiment == "positive":
        ending = "新聞面有助於提升市場關注，但仍需要搭配技術面是否站回多方，以及估值是否合理來判斷。"
    else:
        ending = "目前新聞尚未明顯改變判斷，仍以技術面、估值與價格計畫作為主要觀察依據。"

    return (
        f"近期新聞情緒為{sentiment_label}，影響程度為{impact_level}，"
        f"主要屬於「{impact_type}」。{explanation} {ending}"
    )


def build_ml_reference(context: dict) -> str:
    ml_research = context.get("ml_research") or {}
    if ml_research.get("status") != "success":
        reason = ml_research.get("reason") or ml_research.get("status") or "missing ml_research output"
        return f"這次沒有可用的機器學習參考。原因：{reason}。"

    lines = [
        "以下是模型根據歷史資料、技術特徵、市場環境與新聞摘要產生的參考，不會直接改變本次結論或價格計畫。",
        "",
        "上漲與風險機率：",
    ]
    target_labels = [
        ("up_5d", "5 個交易日後上漲機率"),
        ("up_10d", "10 個交易日後上漲機率"),
        ("up_20d", "20 個交易日後上漲機率"),
        ("large_drop_20d", "20 個交易日內中途大跌風險"),
    ]
    targets = ml_research.get("targets") or {}
    for key, label in target_labels:
        target = targets.get(key) or {}
        probability = to_float(target.get("probability"))
        if probability is None:
            continue
        signal = translate_ml_signal_label(target.get("signal_label"))
        suffix = f"，{signal}" if signal else ""
        lines.append(f"- {label}：{format_percent(probability)}{suffix}。")

    return_reference = ml_research.get("return_reference") or {}
    if has_return_reference(return_reference):
        lines.extend(["", "歷史相似情境參考:"])
        lines.extend(build_return_reference_lines(return_reference))

    return_model = ml_research.get("return_model") or {}
    if return_model.get("status") == "success":
        lines.extend(["", "報酬模型估算:"])
        lines.append("- 這是第一版實驗模型，仍以歷史區間作為主要參考。")
        lines.extend(build_return_model_lines(return_model))

    overlay = ml_research.get("downside_risk_overlay") or {}
    if overlay.get("active"):
        lines.extend(["", "保守風險修正:"])
        lines.append(
            "- "
            f"保守風險層級為 {overlay.get('risk_level')}，"
            f"20 個交易日內中途最大跌幅保守參考約 {format_percent(overlay.get('conservative_max_drop'))}。"
        )
        if overlay.get("reasons"):
            reason_text = "、".join(
                translate_downside_overlay_reason(reason)
                for reason in overlay["reasons"]
            )
            lines.append(f"- 觸發原因：{reason_text}。")

    trust = context.get("ml_reference_trust") or {}
    if trust.get("status") == "reduced_trust":
        lines.append("")
        lines.append("ML Reference 目前為降低信任狀態，相關數字應保守解讀。")

    return "\n".join(lines)


def build_exit_signal_analysis(context: dict) -> str:
    exit_signal = context.get("exit_signal") or {}
    if exit_signal.get("status") != "success":
        return "目前沒有足夠資料形成持有風險或出場觀察。"

    signal = exit_signal.get("exit_signal", "unknown")
    weakening = exit_signal.get("weakening_signal_20d", "unknown")
    reason = remove_duplicate_weakening_reason(exit_signal.get("reason") or "", weakening)
    action_note = exit_signal.get("action_note") or ""
    lines = [
        f"目前 exit signal 為「{signal}」，20 日轉弱風險為「{weakening}」。"
    ]
    if reason:
        lines.append(f"判斷原因：{reason}")
    if action_note:
        lines.append(f"操作觀察：{remove_holding_prefix(action_note)}")
    lines.append("這是持有風險觀察，不是直接買賣指令。")
    return "\n".join(lines)


def remove_duplicate_weakening_reason(reason: str, weakening: str) -> str:
    text = reason.strip()
    if not text:
        return ""

    duplicates = [
        f"20 日轉弱風險為 {weakening}。",
        f"20 日轉弱風險為「{weakening}」。",
        f"20 日轉弱風險為 {weakening}",
        f"20 日轉弱風險為「{weakening}」",
    ]
    for duplicate in duplicates:
        text = text.replace(duplicate, "")
    return " ".join(text.split()).strip()


def remove_holding_prefix(text: str) -> str:
    cleaned = text.strip()
    prefixes = ("若已持有，", "如果已持有，", "若已持有，應", "如果已持有，應")
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    return cleaned


def translate_downside_overlay_reason(reason: str) -> str:
    labels = {
        "price_below_ma20": "價格低於 MA20",
        "macd_histogram_negative": "MACD 動能轉弱",
        "high_20d_volatility": "20 日波動偏高",
        "market_regime_bearish": "市場環境偏弱",
        "market_regime_transition_or_volatile": "市場環境轉換或波動偏高",
        "technical_state_bearish": "技術狀態偏弱",
        "technical_state_volume_surge": "量能異動需要觀察",
        "technical_state_breakout_or_pullback_with_negative_macd": "技術型態仍需搭配動能確認",
        "risk_state_high": "風險狀態偏高",
        "risk_state_elevated": "風險狀態升高",
        "recent_risk_news": "近期有風險類新聞",
    }
    return labels.get(reason, reason)


def build_overall_assessment(context: dict) -> str:
    decision = build_decision(context)
    profile = context.get("research_profile") or {}
    evidence_quality = context.get("evidence_quality") or {}
    risk_level = profile.get("risk_level", "unknown")
    combined_score = to_float(profile.get("combined_score"))
    score_text = f"綜合分數為 {combined_score:.2f}。" if combined_score is not None else "綜合分數目前不足。"
    evidence_text = build_evidence_quality_text(evidence_quality)
    return (
        f"{score_text} 基本面、技術面與新聞面合併後，目前結論為「{decision['conclusion']}」，"
        f"風險等級為 {risk_level}。{evidence_text} "
        "價格計畫可作為後續觀察區間，但不代表現在一定適合進場。"
    )


def build_risk_reminder(context: dict) -> str:
    lines = [
        "- 這份輸出只整理資料與策略訊號，不構成投資建議。",
        "- 新聞、價格資料與回測結果都可能延遲或不完整。",
        "- 進出場仍需要搭配個人風險承受度、部位大小與停損規劃。",
    ]
    data_freshness = context.get("data_freshness") or {}
    warnings = data_freshness.get("warnings") or []
    if warnings:
        lines.append("- 目前有資料新鮮度或完整性提醒，詳細資訊放在 Structured Data。")
    return "\n".join(lines)


def build_decision(context: dict) -> dict:
    valuation = get_valuation_label(context.get("fundamentals") or {})
    technical = get_technical_label(context)
    news_sentiment = ((context.get("news_summary") or {}).get("sentiment")) or "neutral"
    conclusion = get_conclusion_label(valuation, technical, news_sentiment)
    return {"valuation": valuation, "technical": technical, "conclusion": conclusion}


def get_valuation_label(fundamentals: dict) -> str:
    status = fundamentals.get("status")
    if status == "skipped":
        return "未納入基本面"
    if status and status != "success":
        return "估值資料不足"

    metrics = fundamentals.get("metrics") or {}
    trailing_pe = to_float(metrics.get("trailing_pe"))
    forward_pe = to_float(metrics.get("forward_pe"))
    price_to_sales = to_float(metrics.get("price_to_sales"))
    revenue_growth = to_float(metrics.get("revenue_growth"))
    pe = forward_pe if forward_pe is not None else trailing_pe

    if (pe is not None and pe >= 60) or (price_to_sales is not None and price_to_sales >= 20):
        return "明顯偏貴"
    if (pe is not None and pe >= 35) or (price_to_sales is not None and price_to_sales >= 12):
        return "合理偏貴"
    if pe is not None and pe <= 20 and revenue_growth is not None and revenue_growth > 0:
        return "合理偏便宜"
    return "估值中立"


def get_technical_label(context: dict) -> str:
    technical = context.get("technical_analysis") or {}
    signals = context.get("signals") or {}
    if (signals.get("pullback") or {}).get("is_pullback"):
        return "接近支撐觀察區"
    if technical.get("short_term_trend") == "strong" and technical.get("is_above_ma20"):
        return "多方比較有力"
    if technical.get("short_term_trend") == "weak" or technical.get("is_above_ma20") is False:
        return "空方壓力還在"
    if (signals.get("breakout") or {}).get("is_breakout") or (signals.get("volume_surge") or {}).get("is_volume_surge"):
        return "多方剛發動，還要確認"
    return "多空方向不明"


def get_conclusion_label(valuation: str, technical: str, news_sentiment: str) -> str:
    if technical == "空方壓力還在":
        return "暫不進場"
    if valuation == "明顯偏貴":
        return "等待更好價格"
    if technical == "接近支撐觀察區":
        return "觀察回踩是否有效"
    if technical == "多方比較有力" and news_sentiment != "negative":
        return "可列入觀察"
    if news_sentiment == "negative":
        return "降低進場信心"
    return "還需要觀察"


def build_historical_signal_text(backtest_evidence: dict) -> str:
    signals = backtest_evidence.get("signals") or []
    if backtest_evidence.get("status") == "no_triggered_signals" or not signals:
        return "歷史訊號參考：目前沒有明確突破、放量或回踩訊號，因此本次不附加歷史訊號參考。"
    if backtest_evidence.get("status") and backtest_evidence.get("status") != "success":
        message = (backtest_evidence.get("summary") or {}).get("message") or "歷史資料不足，暫時無法建立歷史訊號參考。"
        return f"歷史訊號參考：{message}"
    return "歷史訊號參考：目前有技術訊號樣本，詳細數字放在 Structured Data。"


def build_evidence_quality_text(evidence_quality: dict) -> str:
    if not evidence_quality:
        return "證據品質目前不足。詳細資訊放在 Structured Data。"
    level = evidence_quality.get("level", "unknown")
    return f"證據品質為 {level}，詳細資訊放在 Structured Data。"


def get_news_impact_type(top_topics: dict, sentiment: str) -> str:
    main_topic = "general"
    if top_topics:
        main_topic = max(top_topics.items(), key=lambda item: item[1])[0]
    if main_topic in {"earnings", "guidance", "industry_demand", "earnings_guidance"}:
        return "影響財報預期"
    if main_topic in {"macro", "lawsuit", "probe", "regulator", "risk_event"}:
        return "有風險消息"
    if main_topic == "analyst_rating":
        return "分析師看法改變"
    if main_topic in {"product", "product_demand"}:
        return "有產品或需求題材"
    return "只是市場在關注" if sentiment == "neutral" else "影響短線情緒"


def describe_news_impact_type(impact_type: str) -> str:
    descriptions = {
        "影響財報預期": "這代表新聞跟營收、獲利、財測或產業需求有關，可能會改變市場對公司未來賺多少錢的預期。",
        "有風險消息": "這代表新聞帶來不確定性，例如官司、監管、總經政策或景氣壓力，市場可能會因此變得比較保守。",
        "分析師看法改變": "這代表新聞主要來自分析師升評、降評或目標價調整，通常會影響短線股價情緒，但不一定代表公司體質已經改變。",
        "有產品或需求題材": "這代表新聞和新產品、AI、晶片、server、訂單或需求題材有關，可能提高市場想像空間，但仍要看能不能轉成營收和獲利。",
        "影響短線情緒": "這代表新聞偏正面或負面，但目前比較像短線市場情緒變化，還不一定直接改變公司的基本面。",
        "只是市場在關注": "這代表新聞本身偏中性，表示市場正在討論這檔股票，但方向還不明確。",
    }
    return descriptions.get(impact_type, "這代表新聞有影響，但目前還需要搭配基本面與技術面一起判斷。")


def describe_rsi(rsi14: float) -> str:
    if rsi14 >= 70:
        return "代表短線偏熱，追高要更謹慎。"
    if rsi14 >= 55:
        return "代表買盤動能偏強。"
    if rsi14 <= 30:
        return "代表短線偏弱或接近超賣。"
    if rsi14 <= 45:
        return "代表買盤動能偏弱。"
    return "代表短線動能大致中性。"


def describe_momentum_state(momentum_state: str) -> str:
    descriptions = {
        "bullish": "RSI 與 MACD 顯示多方動能增強，短線買盤相對占優。",
        "turning_positive": "動能正在改善，但仍需要確認能否延續。",
        "turning_negative": "MACD 動能正在轉弱，短線需要留意上漲力道不足。",
        "bearish": "RSI 與 MACD 顯示空方壓力較明顯，短線需要更保守。",
    }
    return descriptions.get(momentum_state, "目前動能訊號不明確，仍需要搭配價格與量能確認。")


def has_return_reference(return_reference: dict) -> bool:
    return any(
        return_reference.get(key)
        for key in [
            "sample_size",
            "expected_return_range_5d",
            "expected_return_range_10d",
            "expected_return_range_20d",
            "max_drop_range_20d",
        ]
    )


def build_return_reference_lines(return_reference: dict) -> list[str]:
    lines = []
    sample_size = return_reference.get("sample_size")
    if sample_size is not None:
        lines.append(f"- 相似樣本數：{sample_size} 筆。")
    if return_reference.get("evidence_quality"):
        lines.append(f"- 證據品質：{translate_quality_label(return_reference['evidence_quality'])}。")
    for key, label in [
        ("expected_return_range_5d", "5 個交易日歷史報酬區間"),
        ("expected_return_range_10d", "10 個交易日歷史報酬區間"),
        ("expected_return_range_20d", "20 個交易日歷史報酬區間"),
        ("max_drop_range_20d", "20 個交易日內中途最大跌幅區間"),
    ]:
        range_text = format_range_percent(return_reference.get(key))
        if range_text != "-":
            lines.append(f"- {label}：{range_text}。")
    return lines or ["- 目前沒有足夠的歷史區間資料。"]


def build_return_model_lines(return_model: dict) -> list[str]:
    labels = [
        ("forward_return_5d", "模型估算 5 個交易日報酬"),
        ("forward_return_10d", "模型估算 10 個交易日報酬"),
        ("forward_return_20d", "模型估算 20 個交易日報酬"),
        ("max_drop_20d", "模型估算 20 個交易日內中途最大跌幅"),
    ]
    targets = return_model.get("targets") or {}
    lines = []
    for key, label in labels:
        target = targets.get(key) or {}
        value = format_signed_percent(target.get("predicted_value"))
        if value == "-":
            continue
        range_text = format_range_percent(target.get("predicted_range"))
        quality = translate_quality_label(target.get("model_quality", "unknown"))
        range_part = f"，估算區間 {range_text}" if range_text != "-" else ""
        lines.append(f"- {label}：{value}{range_part}，模型品質 {quality}。")
    return lines


def translate_ml_signal_label(label: str | None) -> str:
    labels = {
        "bullish": "偏多",
        "bearish": "偏空",
        "slightly_bullish": "稍微偏多",
        "slightly_bearish": "稍微偏空",
        "unclear_direction": "方向不明確",
        "high_large_drop_risk": "中途大跌風險偏高",
        "medium_large_drop_risk": "中途大跌風險中等",
        "low_large_drop_risk": "中途大跌風險偏低",
    }
    normalized = str(label or "").lower().replace("-", "_").replace(" ", "_")
    return labels.get(normalized, str(label or "").replace("_", " "))


def translate_quality_label(label: str | None) -> str:
    labels = {
        "high": "高",
        "medium": "中",
        "low_to_medium": "低到中",
        "low": "低",
        "none": "無",
        "unknown": "未知",
    }
    return labels.get(label, label or "未知")


def format_money(value: float) -> str:
    return f"${value:.0f}"


def format_percent(value) -> str:
    number = to_float(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def format_signed_percent(value) -> str:
    number = to_float(value)
    if number is None:
        return "-"
    sign = "+" if number >= 0 else ""
    return f"{sign}{number * 100:.1f}%"


def format_range_percent(value: dict | None) -> str:
    if not value:
        return "-"
    low = to_float(value.get("low") if "low" in value else value.get("low_percent"))
    high = to_float(value.get("high") if "high" in value else value.get("high_percent"))
    if low is None or high is None:
        return "-"
    if abs(low) > 1 or abs(high) > 1:
        low /= 100
        high /= 100
    return f"{format_signed_percent(low)} ~ {format_signed_percent(high)}"


def to_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
