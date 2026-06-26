def format_bool(value: bool) -> str:
    if value:
        return "是"
    return "否"


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_single_stock_analysis(analysis_data: dict) -> str:
    if analysis_data["status"] != "success":
        return format_error_message(analysis_data)

    technical = analysis_data["technical_analysis"]
    signals = analysis_data["signals"]
    breakout = signals["breakout"]
    volume_surge = signals["volume_surge"]
    pullback = signals["pullback"]
    news_items = analysis_data["news"]
    news_analysis = analysis_data.get(
        "news_analysis",
        {
            "summary": {
                "total_items": 0,
                "sentiment": "neutral",
                "high_importance_count": 0,
                "top_topics": {},
            }
        },
    )
    news_summary = news_analysis["summary"]
    fundamentals = analysis_data.get(
        "fundamentals",
        {
            "status": "skipped",
            "summary": {
                "stance": "unknown",
                "positives": [],
                "risks": [],
            },
        },
    )
    fundamental_summary = fundamentals["summary"]
    research_profile = analysis_data.get(
        "research_profile",
        {
            "technical_score": 0,
            "news_score": 0,
            "fundamental_score": 0,
            "risk_score": 0,
            "combined_score": 0,
            "setup_quality": "unknown",
            "risk_level": "unknown",
            "research_confidence": "low",
            "evidence_quality": {
                "level": "low",
                "reason": "證據品質資料不足。",
            },
        },
    )
    evidence_quality = analysis_data.get(
        "evidence_quality",
        research_profile.get(
            "evidence_quality",
            {
                "level": "low",
                "stock_specific": "unknown",
                "peer_group": "not_used",
                "market_wide": "not_used",
                "data_completeness": "unknown",
                "signal_clarity": "unknown",
                "reason": "證據品質資料不足。",
            },
        ),
    )

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
            f"- 新聞整體情緒：{news_summary['sentiment']}",
            f"- 高重要性新聞數：{news_summary['high_importance_count']}",
            f"- 主要新聞主題：{format_topic_counts(news_summary['top_topics'])}",
            "",
            "基本面摘要",
            f"- 基本面狀態：{fundamentals['status']}",
            f"- 基本面立場：{fundamental_summary['stance']}",
            f"- 正向因素：{format_reason_list(fundamental_summary['positives'])}",
            f"- 風險因素：{format_reason_list(fundamental_summary['risks'])}",
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
            "- 這份輸出只整理資料與策略訊號，不構成投資建議。",
            "- 新聞、價格資料與回測結果都可能延遲或不完整。",
            "- 進出場仍需要搭配個人風險承受度、部位大小與停損規劃。",
        ]
    )

    return "\n".join(lines)


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
        "績效摘要",
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
            "- 回測只代表歷史資料中的規則表現，不代表未來結果。",
            "- 目前回測尚未納入交易成本、滑價、稅費與完整風控。",
            "- 樣本數太少時，勝率和平均報酬的參考價值會下降。",
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
        return "- 歷史結果偏正向，但仍需要搭配風控與更多樣本確認。"

    if metrics["average_return"] <= 0:
        return "- 歷史平均報酬不佳，這個策略在目前資料區間需要謹慎看待。"

    return "- 歷史結果有一定參考價值，但訊號品質仍需要搭配其他條件判斷。"


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
