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


def format_backtest_analysis(backtest_data: dict) -> str:
    if backtest_data["status"] != "success":
        return format_error_message(backtest_data)

    report = backtest_data["report"]
    metrics = report["metrics"]
    sample_trades = report["sample_trades"]

    lines = [
        f"{backtest_data['ticker']} 策略回測摘要",
        "",
        f"原始問題：{backtest_data['user_query']}",
        f"策略：{backtest_data['strategy']}",
        "",
        "績效摘要",
        f"- 總交易次數：{metrics['total_trades']}",
        f"- 勝率：{format_percent(metrics['win_rate'])}",
        f"- 平均報酬：{format_percent(metrics['average_return'])}",
        f"- 最大虧損：{format_percent(metrics['max_loss'])}",
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
    successful_results = [result for result in results if result["status"] == "success"]
    failed_results = [result for result in results if result["status"] != "success"]

    lines = [
        f"{theme_data['theme_name']} 主題觀察清單",
        "",
        f"原始問題：{theme_data['query']}",
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
