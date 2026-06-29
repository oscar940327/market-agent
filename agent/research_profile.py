def build_research_profile(
    technical: dict,
    signals: dict,
    news_analysis: dict,
    fundamentals: dict,
    price_history_rows: int | None = None,
    include_news: bool = True,
    include_fundamentals: bool = True,
    backtest_evidence: dict | None = None,
) -> dict:
    technical_score = calculate_technical_score(technical, signals)
    news_score = calculate_news_score(news_analysis)
    fundamental_score = calculate_fundamental_score(fundamentals)
    evidence_quality = build_evidence_quality(
        technical=technical,
        signals=signals,
        news_analysis=news_analysis,
        fundamentals=fundamentals,
        price_history_rows=price_history_rows,
        include_news=include_news,
        include_fundamentals=include_fundamentals,
        backtest_evidence=backtest_evidence,
    )
    risk_score = calculate_risk_score(
        technical_score=technical_score,
        news_score=news_score,
        fundamental_score=fundamental_score,
        fundamentals=fundamentals,
    )

    combined_score = round(
        technical_score + news_score + fundamental_score - risk_score,
        2,
    )

    return {
        "technical_score": technical_score,
        "news_score": news_score,
        "fundamental_score": fundamental_score,
        "risk_score": risk_score,
        "combined_score": combined_score,
        "setup_quality": classify_setup_quality(combined_score),
        "risk_level": classify_risk_level(risk_score),
        "research_confidence": evidence_quality["level"],
        "evidence_quality": evidence_quality,
    }


def calculate_technical_score(technical: dict, signals: dict) -> float:
    score = 0.0

    if technical["short_term_trend"] == "strong":
        score += 2
    elif technical["short_term_trend"] == "weak":
        score -= 1

    if technical["is_above_ma20"]:
        score += 1
    else:
        score -= 1

    momentum_state = technical.get("momentum_state", "neutral")
    rsi14 = technical.get("rsi14")

    if momentum_state == "bullish_momentum":
        score += 1.5
    elif momentum_state == "turning_positive":
        score += 0.75
    elif momentum_state == "bullish_but_overbought":
        score += 0.5
    elif momentum_state == "bearish_momentum":
        score -= 1.5
    elif momentum_state == "turning_negative":
        score -= 0.75
    elif momentum_state == "bearish_but_oversold":
        score -= 0.5

    if isinstance(rsi14, (int, float)) and rsi14 >= 75:
        score -= 0.5

    if signals["breakout"]["is_breakout"]:
        score += 2

    if signals["volume_surge"]["is_volume_surge"]:
        score += 1.5

    if signals["pullback"]["is_pullback"]:
        score += 1

    return score


def calculate_news_score(news_analysis: dict) -> float:
    summary = news_analysis["summary"]
    sentiment = summary["sentiment"]

    if sentiment == "positive":
        return 1.0

    if sentiment == "negative":
        return -1.0

    return 0.0


def calculate_fundamental_score(fundamentals: dict) -> float:
    summary = fundamentals["summary"]
    positives = len(summary.get("positives", []))
    risks = len(summary.get("risks", []))

    return round((positives * 0.75) - (risks * 0.75), 2)


def calculate_risk_score(
    technical_score: float,
    news_score: float,
    fundamental_score: float,
    fundamentals: dict,
) -> float:
    risk_score = 0.0

    if technical_score < 0:
        risk_score += 1

    if news_score < 0:
        risk_score += 1

    if fundamental_score < 0:
        risk_score += 1

    if fundamentals["status"] != "success":
        risk_score += 0.5

    return risk_score


def classify_setup_quality(combined_score: float) -> str:
    if combined_score >= 4:
        return "strong"

    if combined_score >= 1.5:
        return "neutral_positive"

    if combined_score <= -1:
        return "weak"

    return "neutral"


def classify_risk_level(risk_score: float) -> str:
    if risk_score >= 2:
        return "high"

    if risk_score >= 1:
        return "medium"

    return "low"


def classify_research_confidence(news_analysis: dict, fundamentals: dict) -> str:
    has_news = news_analysis["summary"]["total_items"] > 0
    has_fundamentals = fundamentals["status"] == "success"

    if has_news and has_fundamentals:
        return "high"

    if has_news or has_fundamentals:
        return "medium"

    return "low"


def build_evidence_quality(
    technical: dict,
    signals: dict,
    news_analysis: dict,
    fundamentals: dict,
    price_history_rows: int | None = None,
    include_news: bool = True,
    include_fundamentals: bool = True,
    backtest_evidence: dict | None = None,
) -> dict:
    stock_specific = classify_stock_specific_evidence(price_history_rows)
    backtest_sample = classify_backtest_sample(backtest_evidence)
    news_coverage = classify_news_coverage(
        news_analysis=news_analysis,
        include_news=include_news,
    )
    sentiment_confidence = classify_sentiment_confidence(
        news_analysis=news_analysis,
        news_coverage=news_coverage,
    )
    news_impact_quality = classify_news_impact_quality(
        news_analysis=news_analysis,
        news_coverage=news_coverage,
    )
    fundamental_coverage = classify_fundamental_coverage(
        fundamentals=fundamentals,
        include_fundamentals=include_fundamentals,
    )
    data_completeness = classify_data_completeness(
        news_coverage=news_coverage,
        fundamental_coverage=fundamental_coverage,
        price_history_rows=price_history_rows,
        backtest_sample=backtest_sample,
    )
    signal_clarity = classify_signal_clarity(technical=technical, signals=signals)
    level = classify_evidence_level(
        stock_specific=stock_specific,
        backtest_sample=backtest_sample,
        data_completeness=data_completeness,
        signal_clarity=signal_clarity,
        news_coverage=news_coverage,
        fundamental_coverage=fundamental_coverage,
    )

    return {
        "level": level,
        "stock_specific": stock_specific,
        "backtest_sample": backtest_sample,
        "peer_group": "not_used",
        "market_wide": "not_used",
        "data_completeness": data_completeness,
        "signal_clarity": signal_clarity,
        "news_coverage": news_coverage,
        "social_coverage": "not_used",
        "sentiment_confidence": sentiment_confidence,
        "news_impact_quality": news_impact_quality,
        "fundamental_coverage": fundamental_coverage,
        "price_history_rows": price_history_rows,
        "reason": build_evidence_reason(
            level=level,
            stock_specific=stock_specific,
            backtest_sample=backtest_sample,
            data_completeness=data_completeness,
            signal_clarity=signal_clarity,
            news_coverage=news_coverage,
            fundamental_coverage=fundamental_coverage,
        ),
    }


def classify_stock_specific_evidence(price_history_rows: int | None) -> str:
    if price_history_rows is None:
        return "unknown"

    if price_history_rows >= 200:
        return "medium"

    if price_history_rows >= 60:
        return "low_to_medium"

    return "low"


def classify_data_completeness(
    news_coverage: str,
    fundamental_coverage: str,
    price_history_rows: int | None = None,
    backtest_sample: str = "not_applicable",
) -> str:
    values = quality_values()
    dimensions = [classify_price_data_coverage(price_history_rows)]

    for coverage in [news_coverage, fundamental_coverage, backtest_sample]:
        if coverage not in {"skipped", "not_applicable", "not_used"}:
            dimensions.append(coverage)

    if not dimensions:
        return "low"

    average_score = sum(values.get(value, 0) for value in dimensions) / len(dimensions)

    return quality_from_score(average_score)


def classify_price_data_coverage(price_history_rows: int | None) -> str:
    if price_history_rows is None:
        return "none"

    if price_history_rows >= 200:
        return "high"

    if price_history_rows >= 60:
        return "medium"

    if price_history_rows >= 20:
        return "low_to_medium"

    return "low"


def classify_backtest_sample(backtest_evidence: dict | None) -> str:
    if not backtest_evidence:
        return "not_applicable"

    status = backtest_evidence.get("status")

    if status == "no_triggered_signals":
        return "not_applicable"

    if status != "success":
        return "none"

    signals = backtest_evidence.get("signals", [])

    if not signals:
        return "none"

    values = quality_values()
    score = max(
        values.get(signal.get("evidence_quality", {}).get("level"), 0)
        for signal in signals
    )

    return quality_from_score(score)


def classify_news_coverage(news_analysis: dict, include_news: bool = True) -> str:
    if not include_news:
        return "skipped"

    total_items = int(news_analysis.get("summary", {}).get("total_items", 0))

    if total_items <= 0:
        return "none"

    if total_items == 1:
        return "low_to_medium"

    if total_items == 2:
        return "medium"

    return "high"


def classify_sentiment_confidence(news_analysis: dict, news_coverage: str) -> str:
    if news_coverage in {"skipped", "none"}:
        return news_coverage

    summary = news_analysis.get("summary", {})
    total_items = int(summary.get("total_items", 0))
    sentiment_counts = summary.get("sentiment_counts", {})

    if total_items <= 0 or not sentiment_counts:
        return "low"

    dominant_count = max(sentiment_counts.values())
    dominant_ratio = dominant_count / total_items

    if total_items >= 3 and dominant_ratio >= 0.67:
        return "high"

    if total_items >= 2 and dominant_ratio >= 0.5:
        return "medium"

    return "low_to_medium"


def classify_news_impact_quality(news_analysis: dict, news_coverage: str) -> str:
    if news_coverage in {"skipped", "none"}:
        return news_coverage

    summary = news_analysis.get("summary", {})
    high_importance_count = int(summary.get("high_importance_count", 0))
    top_topics = summary.get("top_topics", {})
    meaningful_topics = {
        "earnings_guidance",
        "risk_event",
        "product_demand",
        "earnings",
        "guidance",
        "industry_demand",
        "analyst_rating",
        "product",
        "macro",
        "lawsuit",
    }
    has_meaningful_topic = any(topic in meaningful_topics for topic in top_topics)

    if high_importance_count >= 2 and has_meaningful_topic:
        return "high"

    if high_importance_count >= 1 or has_meaningful_topic:
        return "medium"

    return "low_to_medium"


def classify_fundamental_coverage(
    fundamentals: dict,
    include_fundamentals: bool = True,
) -> str:
    if not include_fundamentals:
        return "skipped"

    if fundamentals.get("status") != "success":
        return "none"

    metrics = fundamentals.get("metrics", {})
    populated_metrics = [
        value
        for value in metrics.values()
        if value is not None and value != ""
    ]

    if len(populated_metrics) >= 6:
        return "high"

    if len(populated_metrics) >= 3:
        return "medium"

    return "low_to_medium"


def classify_signal_clarity(technical: dict, signals: dict) -> str:
    clear_signals = 0
    conflicting_signals = 0
    momentum_state = technical.get("momentum_state", "neutral")

    if technical.get("short_term_trend") in {"strong", "weak"}:
        clear_signals += 1

    if signals["breakout"]["is_breakout"]:
        clear_signals += 1

    if signals["volume_surge"]["is_volume_surge"]:
        clear_signals += 1

    if signals["pullback"]["is_pullback"]:
        clear_signals += 1

    if momentum_state in {"bullish_momentum", "bearish_momentum"}:
        clear_signals += 1
    elif momentum_state in {"turning_positive", "turning_negative"}:
        clear_signals += 0.5

    if technical.get("short_term_trend") == "strong" and momentum_state in {
        "bearish_momentum",
        "turning_negative",
    }:
        conflicting_signals += 1

    if technical.get("short_term_trend") == "weak" and momentum_state in {
        "bullish_momentum",
        "turning_positive",
    }:
        conflicting_signals += 1

    net_signal_score = clear_signals - conflicting_signals

    if net_signal_score >= 3:
        return "high"

    if net_signal_score >= 1.5:
        return "medium"

    if net_signal_score > 0:
        return "low_to_medium"

    return "low"


def classify_evidence_level(
    stock_specific: str,
    backtest_sample: str,
    data_completeness: str,
    signal_clarity: str,
    news_coverage: str,
    fundamental_coverage: str,
) -> str:
    values = quality_values()
    dimensions = [
        stock_specific,
        data_completeness,
        signal_clarity,
        news_coverage,
        fundamental_coverage,
    ]

    if backtest_sample != "not_applicable":
        dimensions.append(backtest_sample)

    scored_dimensions = [
        value
        for value in dimensions
        if value not in {"skipped", "not_applicable", "not_used"}
    ]

    if not scored_dimensions:
        return "low"

    average_score = (
        sum(values.get(value, 0) for value in scored_dimensions)
        / len(scored_dimensions)
    )

    return quality_from_score(average_score)


def quality_values() -> dict[str, int]:
    return {
        "unknown": 0,
        "none": 0,
        "not_used": 0,
        "not_applicable": 0,
        "skipped": 0,
        "low": 1,
        "low_to_medium": 2,
        "medium": 3,
        "high": 4,
    }


def quality_from_score(score: float) -> str:
    if score >= 3.5:
        return "high"

    if score >= 2.5:
        return "medium"

    if score >= 1.5:
        return "low_to_medium"

    if score > 0:
        return "low"

    return "none"


def build_evidence_reason(
    level: str,
    stock_specific: str,
    backtest_sample: str,
    data_completeness: str,
    signal_clarity: str,
    news_coverage: str,
    fundamental_coverage: str,
) -> str:
    return (
        f"證據品質為 {level}。"
        f"個股價格資料層級為 {stock_specific}，"
        f"歷史訊號樣本為 {backtest_sample}，"
        f"資料完整度為 {data_completeness}，"
        f"訊號清楚度為 {signal_clarity}。"
        f"新聞覆蓋度為 {news_coverage}，"
        f"基本面覆蓋度為 {fundamental_coverage}。"
        "目前尚未使用同產業或全市場相似情境樣本，因此這不是歷史相似案例的完整驗證。"
    )
