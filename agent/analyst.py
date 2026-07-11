from agent.report_context import build_single_stock_report_context
from agent.ml_trust_explanation import format_ml_trust_explanation_lines


def format_bool(value: bool) -> str:
    if value:
        return "是"
    return "否"


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_single_stock_analysis(analysis_data: dict) -> str:
    if analysis_data["status"] != "success":
        return format_error_message(analysis_data)

    context = build_single_stock_report_context(analysis_data)
    technical = context["technical_analysis"]
    signals = context["signals"]
    breakout = signals["breakout"]
    volume_surge = signals["volume_surge"]
    pullback = signals["pullback"]
    news_items = context["news"]
    news_summary = context["news_summary"]
    news_events_summary = context["news_events_summary"]
    fundamentals = context["fundamentals"]
    fundamental_summary = context["fundamental_summary"]
    research_profile = context["research_profile"]
    evidence_quality = context["evidence_quality"]
    ml_research = context["ml_research"]
    ml_reference_trust = context["ml_reference_trust"]
    exit_signal = context["exit_signal"]
    data_freshness = context["data_freshness"]

    lines = [
        f"{analysis_data['ticker']} 單一股票分析",
        "",
        f"原始問題：{analysis_data['query']}",
        "",
        "技術面摘要",
        f"- 最新收盤價：{technical['current_price']}",
        f"- MA10：{technical['ma10']}",
        f"- MA20：{technical['ma20']}",
        f"- MA50：{technical['ma50']}",
        f"- 價格是否高於 MA20：{format_bool(technical['is_above_ma20'])}",
        f"- 短線趨勢：{technical['short_term_trend']}",
        f"- RSI14：{technical.get('rsi14', 'unknown')}",
        f"- MACD：{technical.get('macd', 'unknown')}",
        f"- MACD signal：{technical.get('macd_signal', 'unknown')}",
        f"- MACD histogram：{technical.get('macd_histogram', 'unknown')}",
        f"- 動能狀態：{technical.get('momentum_state', 'unknown')}",
        "",
        "策略訊號",
        (
            f"- 突破訊號：{format_bool(breakout['is_breakout'])} "
            f"(最新收盤 {breakout['latest_close']}，前高 {breakout['previous_high']})"
        ),
        (
            f"- 成交量放大：{format_bool(volume_surge['is_volume_surge'])} "
            f"(量比 {volume_surge['volume_ratio']}，門檻 {volume_surge['surge_multiplier']})"
        ),
        (
            f"- MA20 回測：{format_bool(pullback['is_pullback'])} "
            f"(距離 MA20 {format_percent(pullback['distance_from_ma20'])})"
        ),
        "",
        "近期新聞",
    ]

    if news_items:
        for news in news_items:
            lines.append(f"- {news['published']} | {news['title']}")
            lines.append(f"  {news['link']}")
    else:
        lines.append("- 目前沒有取得新聞資料。")

    lines.extend(
        [
            "",
            "新聞結構化摘要",
            *format_news_summary_lines(news_summary, news_events_summary),
            "",
            "基本面摘要",
            f"- 基本面狀態：{fundamentals['status']}",
            f"- 基本面立場：{fundamental_summary['stance']}",
            f"- 正向因素：{format_reason_list(fundamental_summary['positives'])}",
            f"- 風險因素：{format_reason_list(fundamental_summary['risks'])}",
            "",
            "ML Reference",
            *format_ml_reference_lines(ml_research, ml_reference_trust),
            "",
            "持有風險 / 出場觀察",
            *format_exit_signal_lines(exit_signal),
            "",
            "綜合研究評估",
            f"- 技術分數：{research_profile['technical_score']}",
            f"- 新聞分數：{research_profile['news_score']}",
            f"- 基本面分數：{research_profile['fundamental_score']}",
            f"- 風險分數：{research_profile['risk_score']}",
            f"- 綜合分數：{research_profile['combined_score']}",
            f"- setup quality：{research_profile['setup_quality']}",
            f"- risk level：{research_profile['risk_level']}",
            f"- research confidence：{research_profile['research_confidence']}",
            "",
            "證據品質",
            f"- evidence level：{evidence_quality['level']}",
            f"- stock specific：{evidence_quality.get('stock_specific', 'unknown')}",
            f"- peer group：{evidence_quality.get('peer_group', 'not_used')}",
            f"- market wide：{evidence_quality.get('market_wide', 'not_used')}",
            f"- data completeness：{evidence_quality.get('data_completeness', 'unknown')}",
            f"- signal clarity：{evidence_quality.get('signal_clarity', 'unknown')}",
            f"- 說明：{evidence_quality['reason']}",
        ]
    )

    lines.extend(
        [
            "",
            "研究結論",
            build_single_stock_takeaway(technical, signals),
            "",
            "風險提醒",
            *format_data_freshness_warning_lines(data_freshness),
            "- 這份輸出只整理資料與策略訊號，不構成投資建議。",
            "- 新聞、價格資料與回測結果都可能延遲或不完整。",
            "- 進出場仍需要搭配個人風險承受度、部位大小與停損規劃。",
            *format_exit_signal_risk_note_lines(exit_signal),
            *format_ml_risk_note_lines(ml_research),
        ]
    )

    return "\n".join(lines)


def format_exit_signal_lines(exit_signal: dict | None) -> list[str]:
    if not exit_signal:
        return ["- 目前沒有 exit / weakening signal 資料。"]

    if exit_signal.get("status") != "success":
        return [
            f"- 狀態：{exit_signal.get('status', 'unknown')}",
            f"- 說明：{exit_signal.get('reason', '出場觀察資料不足。')}",
        ]

    lines = [
        f"- exit signal：{exit_signal.get('exit_signal', 'unknown')}",
        f"- 20 日轉弱風險：{exit_signal.get('weakening_signal_20d', 'unknown')}",
        f"- 說明：{exit_signal.get('reason', '')}",
        f"- 觀察動作：{exit_signal.get('action_note', '')}",
    ]
    reasons = exit_signal.get("reasons") or []
    if reasons:
        lines.append("- 觸發原因：")
        lines.extend(f"  - {reason}" for reason in reasons)
    return lines


def format_exit_signal_risk_note_lines(exit_signal: dict | None) -> list[str]:
    if not exit_signal or exit_signal.get("status") != "success":
        return []

    if exit_signal.get("exit_signal") in {"reduce", "exit"}:
        return [
            (
                "- 出場觀察提醒：目前出現較明顯轉弱訊號，"
                "若已持有，應重新檢查停損、部位大小與原本的出場計畫。"
            )
        ]

    return []


def format_data_freshness_warning_lines(data_freshness: dict | None) -> list[str]:
    if not data_freshness:
        return []

    warnings = data_freshness.get("warnings", [])
    if not warnings:
        return []

    lines = ["- 資料新鮮度提醒："]
    for warning in warnings:
        status = warning.get("status", "unknown")
        message = warning.get("message") or warning.get("reason") or "資料狀態需要確認。"
        lines.append(f"  - {status}: {message}")

    return lines


def format_ml_reference_lines(
    ml_research: dict | None,
    ml_reference_trust: dict | None = None,
) -> list[str]:
    trust = ml_reference_trust or {}
    if not ml_research:
        return [
            *format_ml_trust_lines(trust),
            "- ML reference is currently unavailable. Reason: missing ml_research output.",
        ]

    status = ml_research.get("status")
    if status != "success":
        reason = ml_research.get("reason") or status or "unknown"
        message = ml_research.get("message")
        source_line = format_ml_source_line(ml_research.get("source"))
        line = f"- ML reference is currently unavailable. Reason: {reason}."
        if message:
            line += f" Detail: {message}"
        return [
            *format_ml_trust_lines(trust),
            *([source_line] if source_line else []),
            line,
        ]

    targets = ml_research.get("targets", {})
    lines = [
        *format_ml_trust_lines(trust),
        *format_optional_ml_source_line(ml_research.get("source")),
        format_ml_target_line(
            label="5-day upside probability",
            target=targets.get("up_5d"),
        ),
        format_ml_target_line(
            label="10-day upside probability",
            target=targets.get("up_10d"),
        ),
        format_ml_target_line(
            label="20-day upside probability",
            target=targets.get("up_20d"),
        ),
        *format_ml_20d_policy_lines(trust, "upside"),
        format_ml_target_line(
            label="20-day large-drop risk",
            target=targets.get("large_drop_20d"),
        ),
        *format_ml_20d_policy_lines(trust, "large_drop"),
        f"- {format_ml_quality_sentence(targets)}",
        *format_return_reference_lines(ml_research.get("return_reference")),
        *format_return_model_lines(ml_research.get("return_model")),
    ]

    risk_note = ml_research.get("risk_note")
    if risk_note:
        lines.append(f"- {risk_note}")

    return lines


def format_ml_trust_lines(ml_reference_trust: dict | None) -> list[str]:
    if not ml_reference_trust:
        return []

    explanation_lines = format_ml_trust_explanation_lines(
        ml_reference_trust.get("explanation")
    )
    if explanation_lines:
        return explanation_lines

    label = ml_reference_trust.get("label") or ml_reference_trust.get("status", "unknown")
    display_note = ml_reference_trust.get("display_note") or ""
    reason = ml_reference_trust.get("reason")
    lines = [f"- 信任狀態：{label}。{display_note}"]
    if reason:
        lines.append(f"- 信任狀態原因：{reason}")
    return lines


def format_ml_20d_policy_lines(ml_reference_trust: dict | None, output: str) -> list[str]:
    if not ml_reference_trust or ml_reference_trust.get("status") != "reduced_trust":
        return []

    affected = set(ml_reference_trust.get("affected_outputs") or [])
    if output == "upside" and "20_day_upside_probability" in affected:
        return [
            "- 20 日預測提醒：目前 20 日模型表現較不穩，這個數字應保守看待。",
        ]
    if output == "large_drop":
        return [
            "- 大跌風險提醒：這個數字應作為風險控管參考，不應單獨作為出場依據。",
        ]
    return []


def format_optional_ml_source_line(source: dict | None) -> list[str]:
    line = format_ml_source_line(source)
    return [line] if line else []


def format_ml_source_line(source: dict | None) -> str | None:
    if not source:
        return None

    source_type = source.get("type", "unknown")
    if source_type == "saved_daily_prediction":
        data_as_of = source.get("data_as_of", "unknown")
        freshness = source.get("prediction_freshness", "unknown")
        model_version = source.get("model_version", "unknown")
        return (
            "- ML source: saved daily prediction "
            f"(data as of {data_as_of}, freshness {freshness}, model {model_version})."
        )

    if source_type == "runtime_fallback":
        reason = source.get("reason", "unknown")
        return f"- ML source: runtime fallback. Reason: {reason}."

    if source_type == "unavailable":
        reason = source.get("reason", "unknown")
        return f"- ML source: unavailable. Reason: {reason}."

    if source_type == "skipped":
        reason = source.get("reason", "unknown")
        return f"- ML source: skipped. Reason: {reason}."

    return f"- ML source: {source_type}."


def format_ml_target_line(*, label: str, target: dict | None) -> str:
    if not target:
        return f"- {label}: unavailable"

    probability_percent = target.get("probability_percent")
    signal_label = target.get("signal_label", "unknown")
    if probability_percent is None:
        return f"- {label}: unavailable ({signal_label})"

    return f"- {label}: {probability_percent:.1f}% ({signal_label})"


def format_ml_quality_sentence(targets: dict) -> str:
    upside_qualities = [
        (targets.get(target) or {}).get("signal_quality", "unknown")
        for target in ["up_5d", "up_10d", "up_20d"]
    ]
    large_drop_quality = (targets.get("large_drop_20d") or {}).get(
        "signal_quality",
        "unknown",
    )
    upside_quality = summarize_quality_group(upside_qualities)
    return (
        "Model quality: upside direction signals are "
        f"{upside_quality}, while large-drop risk signal quality is "
        f"{large_drop_quality}. These numbers are reference-only."
    )


def summarize_quality_group(qualities: list[str]) -> str:
    values = {
        "unknown": 0,
        "low": 1,
        "low_to_medium": 2,
        "medium": 3,
        "high": 4,
    }
    scores = [values.get(quality, 0) for quality in qualities]
    if not scores:
        return "unknown"

    average = sum(scores) / len(scores)
    if average >= 3.5:
        return "high"
    if average >= 2.5:
        return "medium"
    if average >= 1.5:
        return "low_to_medium"
    if average > 0:
        return "low"
    return "unknown"


def format_ml_risk_note_lines(ml_research: dict | None) -> list[str]:
    if not ml_research or ml_research.get("status") != "success":
        return []

    risk_note = ml_research.get("risk_note")
    if not risk_note:
        return []

    return [f"- {risk_note}"]


def format_return_reference_lines(return_reference: dict | None) -> list[str]:
    if not return_reference:
        return []

    method = return_reference.get("method", "unknown")
    sample_size = return_reference.get("sample_size")
    evidence_quality = return_reference.get("evidence_quality", "unknown")
    lines = [
        (
            "- Return reference: "
            f"{method}, sample size {sample_size}, evidence quality {evidence_quality}."
        )
    ]

    for horizon in ["5d", "10d", "20d"]:
        expected_range = return_reference.get(f"expected_return_range_{horizon}")
        upside_range = return_reference.get(f"upside_return_range_{horizon}")
        average_return = return_reference.get(f"historical_average_return_{horizon}")
        if expected_range:
            lines.append(
                "- "
                f"{horizon} expected return range: "
                f"{format_return_value(expected_range.get('low'))} ~ "
                f"{format_return_value(expected_range.get('high'))}; "
                f"historical average {format_return_value(average_return)}."
            )
        if upside_range:
            lines.append(
                "- "
                f"{horizon} upside scenario range: "
                f"{format_return_value(upside_range.get('low'))} ~ "
                f"{format_return_value(upside_range.get('high'))}."
            )

    max_drop_range = return_reference.get("max_drop_range_20d")
    if max_drop_range:
        lines.append(
            "- "
            "20d max-drop range: "
            f"{format_return_value(max_drop_range.get('low'))} ~ "
            f"{format_return_value(max_drop_range.get('high'))}."
        )

    note = return_reference.get("note")
    if note:
        lines.append(f"- {note}")

    return lines


def format_return_value(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_return_model_lines(return_model: dict | None) -> list[str]:
    if not return_model:
        return []

    if return_model.get("status") != "success":
        reason = return_model.get("reason", "unknown")
        return [
            f"- Return model is currently unavailable. Reason: {reason}. Historical range remains the primary reference.",
        ]

    targets = return_model.get("targets", {})
    lines = [
        "- Return model: experimental reference only. Historical range remains the primary reference.",
        format_return_model_target_line(
            label="Predicted 5d return",
            target=targets.get("forward_return_5d"),
        ),
        format_return_model_target_line(
            label="Predicted 10d return",
            target=targets.get("forward_return_10d"),
        ),
        format_return_model_target_line(
            label="Predicted 20d return",
            target=targets.get("forward_return_20d"),
        ),
        format_return_model_target_line(
            label="Predicted 20d max drop",
            target=targets.get("max_drop_20d"),
        ),
    ]
    summary = return_model.get("summary")
    if summary:
        lines.append(f"- {summary}")
    return lines


def format_return_model_target_line(*, label: str, target: dict | None) -> str:
    if not target:
        return f"- {label}: unavailable"

    predicted_percent = target.get("predicted_percent")
    predicted_range = target.get("predicted_range") or {}
    model_quality = target.get("model_quality", "unknown")
    return (
        f"- {label}: {format_percent_value(predicted_percent)} "
        f"(range {format_percent_value(predicted_range.get('low_percent'))} ~ "
        f"{format_percent_value(predicted_range.get('high_percent'))}, "
        f"quality {model_quality})"
    )


def format_percent_value(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def build_single_stock_takeaway(technical: dict, signals: dict) -> str:
    positive_signals = []
    risk_signals = []

    if technical["short_term_trend"] == "strong":
        positive_signals.append("短線均線排列偏強")
    elif technical["short_term_trend"] == "weak":
        risk_signals.append("短線均線排列偏弱")

    momentum_state = technical.get("momentum_state")

    if momentum_state == "bullish_momentum":
        positive_signals.append("RSI 與 MACD 顯示多方動能增強")
    elif momentum_state == "turning_positive":
        positive_signals.append("MACD 動能正在轉正")
    elif momentum_state == "bullish_but_overbought":
        risk_signals.append("RSI 偏高，短線可能過熱")
    elif momentum_state == "bearish_momentum":
        risk_signals.append("RSI 與 MACD 顯示空方動能仍在")
    elif momentum_state == "turning_negative":
        risk_signals.append("MACD 動能正在轉弱")
    elif momentum_state == "bearish_but_oversold":
        positive_signals.append("RSI 偏低，可能進入超跌觀察區")

    if signals["breakout"]["is_breakout"]:
        positive_signals.append("價格出現突破訊號")

    if signals["volume_surge"]["is_volume_surge"]:
        positive_signals.append("成交量明顯放大")

    if signals["pullback"]["is_pullback"]:
        positive_signals.append("價格接近 MA20 回測區")

    if not technical["is_above_ma20"]:
        risk_signals.append("價格低於 MA20")

    if positive_signals and risk_signals:
        return (
            "- 目前同時有正向訊號與風險訊號。"
            f"正向：{'、'.join(positive_signals)}；"
            f"風險：{'、'.join(risk_signals)}。"
        )

    if positive_signals:
        return f"- 目前偏正向的訊號包含：{'、'.join(positive_signals)}。"

    if risk_signals:
        return f"- 目前需要優先留意：{'、'.join(risk_signals)}。"

    return "- 目前訊號偏中性，沒有明確突破、放量或 MA20 回測訊號。"


def format_topic_counts(topic_counts: dict) -> str:
    if not topic_counts:
        return "無"

    return "、".join(
        f"{topic} {count}"
        for topic, count in sorted(
            topic_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )


def format_news_summary_lines(
    news_summary: dict,
    news_events_summary: dict | None = None,
) -> list[str]:
    if news_events_summary and news_events_summary.get("status") == "success":
        return [
            (
                f"- 近 {news_events_summary['lookback_days']} 天新聞數："
                f"{news_events_summary['total_events']}"
            ),
            f"- 新聞整體情緒：{format_sentiment(news_events_summary['overall_sentiment'])}",
            (
                f"- 主要新聞主題："
                f"{news_events_summary.get('dominant_topic_label') or '一般新聞'}"
            ),
            f"- 高重要性新聞數：{news_events_summary['high_importance_count']}",
            format_news_impact_takeaway(news_events_summary),
            *format_representative_news(news_events_summary),
        ]

    if news_events_summary and news_events_summary.get("status") == "no_recent_news":
        return [
            f"- 近 {news_events_summary['lookback_days']} 天沒有近期新聞資料。",
            "- 新聞面暫時不調整整體判斷，仍以技術面、估值與風險控管為主。",
        ]

    return [
        f"- 新聞整體情緒：{format_sentiment(news_summary.get('sentiment', 'unknown'))}",
        f"- 高重要性新聞數：{news_summary.get('high_importance_count', 0)}",
        f"- 主要新聞主題：{format_topic_counts(news_summary.get('top_topics', {}))}",
    ]


def format_representative_news(news_events_summary: dict) -> list[str]:
    events = news_events_summary.get("representative_events", [])

    if not events:
        return []

    lines = ["- 代表性新聞："]
    for event in events[:3]:
        published = (event.get("published_at") or "")[:10]
        title = event.get("title") or "未命名新聞"
        source = event.get("source") or "unknown"
        lines.append(f"  - {published} | {source} | {title}")

    return lines


def format_news_impact_takeaway(news_events_summary: dict) -> str:
    sentiment = news_events_summary.get("overall_sentiment", "unknown")
    topic_label = news_events_summary.get("dominant_topic_label") or "一般新聞"
    high_importance_count = news_events_summary.get("high_importance_count", 0)

    if sentiment == "positive":
        prefix = "新聞面偏利多"
    elif sentiment == "negative":
        prefix = "新聞面偏利空"
    elif sentiment == "neutral":
        prefix = "新聞面大致中立"
    else:
        prefix = "新聞面方向不明"

    if high_importance_count > 0:
        return (
            f"- 影響解讀：{prefix}，主要屬於「{topic_label}」，"
            "但仍需搭配技術面與估值，不會單獨改變結論。"
        )

    return (
        f"- 影響解讀：{prefix}，主要屬於「{topic_label}」，"
        "目前較適合作為觀察依據，不應單獨當成進出場理由。"
    )


def format_sentiment(sentiment: str) -> str:
    labels = {
        "positive": "偏利多",
        "negative": "偏利空",
        "neutral": "中立",
        "unknown": "未知",
    }
    return labels.get(sentiment, sentiment)


def format_reason_list(reasons: list[str]) -> str:
    if not reasons:
        return "無"

    return "、".join(reasons)


def format_backtest_analysis(backtest_data: dict) -> str:
    if backtest_data["status"] != "success":
        return format_error_message(backtest_data)

    report = backtest_data["report"]
    metrics = report["metrics"]
    evidence_quality = report.get(
        "evidence_quality",
        backtest_data.get(
            "evidence_quality",
            {
                "level": "unknown",
                "sample_size": metrics["total_trades"],
                "sample_quality": "unknown",
                "history_years": 0,
                "required_history_years": 15,
                "market_cycle_coverage": "unknown",
                "peer_group_needed": True,
                "peer_group": "not_used",
                "reason": "尚未產生回測證據品質。",
            },
        ),
    )
    data_window = report.get("data_window") or backtest_data.get("data_window") or {}
    sample_trades = report["sample_trades"]

    lines = [
        f"{backtest_data['ticker']} 策略回測摘要",
        "",
        f"原始問題：{backtest_data['user_query']}",
        f"策略：{backtest_data['strategy']}",
        "",
        "資料範圍",
        f"- 起始日：{data_window.get('data_start_date', 'unknown')}",
        f"- 結束日：{data_window.get('data_end_date', 'unknown')}",
        f"- data as of：{data_window.get('data_as_of', 'unknown')}",
        f"- 歷史年限：約 {evidence_quality.get('history_years', 0)} 年",
        "",
        "訊號歷史統計",
        f"- 總交易次數：{metrics['total_trades']}",
        f"- 勝率：{format_percent(metrics['win_rate'])}",
        f"- 平均報酬：{format_percent(metrics['average_return'])}",
        f"- 最大虧損：{format_percent(metrics['max_loss'])}",
        "",
        "證據品質",
        f"- 等級：{evidence_quality['level']}",
        f"- 樣本品質：{evidence_quality.get('sample_quality', 'unknown')}",
        f"- 市場週期覆蓋：{evidence_quality.get('market_cycle_coverage', 'unknown')}",
        f"- 需要同類型股票補充：{format_bool(evidence_quality.get('peer_group_needed', True))}",
        f"- peer group：{evidence_quality.get('peer_group', 'not_used')}",
        f"- 說明：{evidence_quality['reason']}",
        "",
        "範例交易",
    ]

    if sample_trades:
        for trade in sample_trades:
            lines.append(
                "- "
                f"{trade['signal_date']} | "
                f"進場 {trade['entry_price']} | "
                f"出場 {trade['exit_price']} | "
                f"{trade['holding_days']} 日報酬 {format_percent(trade['return_pct'])}"
            )
    else:
        lines.append("- 這段資料中沒有出現符合條件的交易。")

    lines.extend(
        [
            "",
            "研究結論",
            build_backtest_takeaway(metrics),
            "",
            "風險提醒",
            "- 這份結果是訊號出現後的歷史統計，不等同於可直接交易的完整策略績效。",
            "- 回測只代表歷史資料中的規則表現，不代表未來結果。",
            "- 目前回測尚未納入交易成本、滑價、稅費與完整風控。",
            build_backtest_validation_note(evidence_quality),
        ]
    )

    return "\n".join(lines)


def format_theme_analysis(theme_data: dict) -> str:
    if theme_data["status"] != "success":
        lines = [
            "主題觀察清單無法完成",
            "",
            f"狀態：{theme_data['status']}",
            f"原因：{theme_data['message']}",
        ]

        supported_themes = theme_data.get("supported_themes", [])

        if supported_themes:
            lines.append("")
            lines.append("目前支援主題：")
            for theme_name in supported_themes:
                lines.append(f"- {theme_name}")

        return "\n".join(lines)

    results = theme_data["results"]
    sector_summary = theme_data.get(
        "sector_summary",
        {
            "successful_count": 0,
            "average_score": 0,
            "strongest_ticker": None,
            "positive_breadth": 0,
            "breadth_label": "no_data",
        },
    )
    scan_scope = theme_data.get(
        "scan_scope",
        {
            "available_ticker_count": len(results),
            "scanned_ticker_count": len(results),
            "scan_limit": None,
            "scan_limited": False,
        },
    )
    successful_results = [result for result in results if result["status"] == "success"]
    failed_results = [result for result in results if result["status"] != "success"]

    lines = [
        f"{theme_data['theme_name']} 主題觀察清單",
        "",
        f"原始問題：{theme_data['query']}",
        "",
        "掃描範圍",
        f"- 可用股票數：{scan_scope['available_ticker_count']}",
        f"- 本次掃描數：{scan_scope['scanned_ticker_count']}",
        f"- 掃描限制：{scan_scope['scan_limit'] or '無'}",
        "",
        "主題廣度摘要",
        f"- 成功分析檔數：{sector_summary['successful_count']}",
        f"- 平均分數：{sector_summary['average_score']}",
        f"- 最強標的：{sector_summary['strongest_ticker']}",
        f"- 正分比例：{format_percent(sector_summary['positive_breadth'])}",
        f"- 廣度狀態：{sector_summary['breadth_label']}",
        "",
        "值得優先觀察",
    ]

    if successful_results:
        for index, result in enumerate(successful_results[:5], start=1):
            analysis = result["analysis"]
            technical = analysis["technical_analysis"]
            signals = analysis["signals"]
            reasons = "、".join(result["reasons"])

            lines.extend(
                [
                    (
                        f"{index}. {result['ticker']} | "
                        f"分數 {result['score']:.1f} | "
                        f"{reasons}"
                    ),
                    (
                        f"   價格 {technical['current_price']} | "
                        f"趨勢 {technical['short_term_trend']} | "
                        f"突破 {format_bool(signals['breakout']['is_breakout'])} | "
                        f"放量 {format_bool(signals['volume_surge']['is_volume_surge'])} | "
                        f"MA20 回測 {format_bool(signals['pullback']['is_pullback'])}"
                    ),
                ]
            )
    else:
        lines.append("- 目前沒有成功完成分析的標的。")

    if failed_results:
        lines.append("")
        lines.append("未完成分析")

        for result in failed_results:
            lines.append(f"- {result['ticker']}：{result['status']}，{result['reasons'][0]}")

    lines.extend(
        [
            "",
            "研究結論",
            build_theme_takeaway(successful_results),
            "",
            "風險提醒",
            "- 這份清單是依照技術訊號排序，不構成投資建議。",
            "- 主題股票池目前是固定清單，可能不完整或需要人工調整。",
            "- 多股票掃描只適合找觀察名單，不能取代完整單股研究。",
        ]
    )

    return "\n".join(lines)


def build_theme_takeaway(results: list[dict]) -> str:
    if not results:
        return "- 目前沒有足夠資料產生主題觀察結論。"

    top_result = results[0]

    if top_result["score"] >= 4:
        return (
            f"- {top_result['ticker']} 目前在這個主題中訊號最集中，"
            "可以優先加入觀察清單。"
        )

    if top_result["score"] >= 2:
        return (
            f"- {top_result['ticker']} 目前相對較強，但整體訊號仍需要搭配單股分析確認。"
        )

    return "- 目前主題內標的訊號不算明確，適合先觀察，不適合直接下結論。"


def build_backtest_takeaway(metrics: dict) -> str:
    total_trades = metrics["total_trades"]

    if total_trades == 0:
        return "- 目前資料區間內沒有符合條件的交易，暫時無法評估策略表現。"

    if total_trades < 10:
        return "- 交易樣本數偏少，這份回測只能當作初步參考。"

    if metrics["win_rate"] >= 0.5 and metrics["average_return"] > 0:
        return "- 歷史結果偏正向，但仍需通過樣本外期間、交易成本與不同市場環境驗證。"

    if metrics["average_return"] <= 0:
        return "- 歷史平均報酬不佳，這個策略在目前資料區間需要謹慎看待。"

    return "- 歷史結果有一定參考價值，但訊號品質仍需要搭配其他條件判斷。"


def build_backtest_validation_note(evidence_quality: dict) -> str:
    sample_quality = evidence_quality.get("sample_quality", "unknown")
    sample_size = int(evidence_quality.get("sample_size") or 0)
    if sample_quality == "high" or sample_size >= 50:
        return "- 本次樣本數充足；下一步重點是樣本外驗證、基準比較與不同市場環境下的穩定性。"
    if sample_size >= 10:
        return "- 本次樣本數可作初步參考，但仍需累積更多樣本並進行樣本外驗證。"
    return "- 本次樣本數偏少，勝率與平均報酬只能作為初步參考。"


def format_portfolio_analysis(portfolio_data: dict) -> str:
    if portfolio_data["status"] != "success":
        return format_error_message(portfolio_data)

    portfolio = portfolio_data["portfolio"]
    concentration = portfolio_data["concentration"]
    theme_exposure = portfolio_data["theme_exposure"]
    risk_summary = portfolio_data["risk_summary"]
    positions = portfolio["positions"]

    lines = [
        "投資組合研究摘要",
        "",
        f"原始問題：{portfolio_data['query']}",
        "",
        "持股概況",
        f"- 持股檔數：{concentration['holding_count']}",
        (
            f"- 最大持股：{concentration['largest_position']} "
            f"({format_percent(concentration['largest_weight'])})"
        ),
        f"- 前三大持股權重：{format_percent(concentration['top_3_weight'])}",
        f"- 持股集中度：{concentration['position_concentration']}",
        "",
        "主題曝險",
        (
            f"- 最大主題：{theme_exposure['largest_theme']} "
            f"({format_percent(theme_exposure['largest_theme_weight'])})"
        ),
        f"- 主題集中度：{theme_exposure['theme_concentration']}",
        f"- 主題分布：{format_weight_map(theme_exposure['exposure'])}",
        "",
        "Portfolio Risk",
        f"- 風險等級：{risk_summary['risk_level']}",
        f"- 主要風險：{format_reason_list(risk_summary['risk_factors'])}",
        "",
        "持股檢查",
    ]

    if positions:
        for position in positions:
            lines.append(
                "- "
                f"{position['ticker']} | "
                f"權重 {format_percent(position['weight'])} | "
                f"趨勢 {position.get('short_term_trend', 'unknown')} | "
                f"setup {position.get('setup_quality', 'unknown')} | "
                f"risk {position.get('risk_level', 'unknown')}"
            )
            lines.append(f"  風險旗標：{format_reason_list(position['risk_flags'])}")
    else:
        lines.append("- 目前沒有可檢查的持股。")

    lines.extend(
        [
            "",
            "研究結論",
            build_portfolio_takeaway(concentration, theme_exposure, risk_summary),
            "",
            "風險提醒",
            "- 這份輸出只整理持股集中度、主題曝險與單股研究訊號，不構成投資建議。",
            "- 權重若未提供 market_value，系統會用等權重估算。",
            "- Portfolio 風險仍需要搭配個人現金流、投資期限與可承受回撤判斷。",
        ]
    )

    return "\n".join(lines)


def format_weight_map(weight_map: dict) -> str:
    if not weight_map:
        return "無"

    return "、".join(
        f"{name} {format_percent(weight)}"
        for name, weight in weight_map.items()
    )


def build_portfolio_takeaway(
    concentration: dict,
    theme_exposure: dict,
    risk_summary: dict,
) -> str:
    if risk_summary["risk_level"] == "high":
        return (
            "- 目前投資組合主要問題是集中度偏高，"
            "應優先檢查最大持股、前三大持股與最大主題曝險。"
        )

    if risk_summary["risk_level"] == "medium":
        return (
            "- 目前投資組合有中等程度的集中或單股風險，"
            "適合持續追蹤權重變化與弱勢標的。"
        )

    if (
        concentration["position_concentration"] == "low"
        and theme_exposure["theme_concentration"] == "low"
    ):
        return "- 目前持股與主題曝險相對分散，沒有明顯 portfolio-level 風險旗標。"

    return "- 目前投資組合風險偏低，但仍需要定期檢查主題曝險與單股趨勢。"


def format_error_message(result: dict) -> str:
    title = "分析無法完成"

    if result.get("ticker"):
        title = f"{result['ticker']} 分析無法完成"

    return "\n".join(
        [
            title,
            "",
            f"狀態：{result['status']}",
            f"原因：{result['message']}",
        ]
    )
