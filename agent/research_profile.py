def build_research_profile(
    technical: dict,
    signals: dict,
    news_analysis: dict,
    fundamentals: dict,
) -> dict:
    technical_score = calculate_technical_score(technical, signals)
    news_score = calculate_news_score(news_analysis)
    fundamental_score = calculate_fundamental_score(fundamentals)
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
        "research_confidence": classify_research_confidence(
            news_analysis=news_analysis,
            fundamentals=fundamentals,
        ),
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
