from agent.ml_reference_trust import build_ml_reference_trust
from agent.rule_based_router import SINGLE_STOCK_HOLDING_TERMS, query_contains_any


def classify_single_stock_question_type(query: str | None) -> str:
    if not query:
        return "entry_or_research"

    lowered = query.lower()
    if query_contains_any(query, lowered, SINGLE_STOCK_HOLDING_TERMS):
        return "holding_exit"

    return "entry_or_research"


def build_single_stock_report_context(data: dict) -> dict:
    news_analysis = data.get("news_analysis", default_news_analysis())
    fundamentals = data.get("fundamentals", default_fundamentals())
    research_profile = data.get("research_profile", default_research_profile())
    evidence_quality = data.get(
        "evidence_quality",
        research_profile.get("evidence_quality", default_evidence_quality()),
    )
    ml_research = (
        data.get("ml_research")
        or (data.get("agent_outputs", {}).get("ml_research") or {}).get("payload")
        or data.get("agent_outputs", {}).get("ml_research")
    )
    ml_prediction = data.get("ml_prediction")
    ml_reference_trust = (
        data.get("ml_reference_trust")
        or (ml_research or {}).get("ml_reference_trust")
        or build_ml_reference_trust(ml_research, ml_prediction)
    )

    return {
        "kind": "single_stock",
        "intent": data.get("intent"),
        "status": data.get("status"),
        "ticker": data.get("ticker"),
        "query": data.get("query"),
        "question_type": data.get("question_type")
        or classify_single_stock_question_type(data.get("query")),
        "execution_plan": data.get("execution_plan", []),
        "price_source": data.get("price_source"),
        "technical_analysis": data.get("technical_analysis"),
        "signals": data.get("signals"),
        "news": data.get("news", []),
        "news_analysis": news_analysis,
        "news_summary": news_analysis.get("summary", {}),
        "news_events_summary": extract_news_events_summary(data),
        "fundamentals": fundamentals,
        "fundamental_summary": fundamentals.get("summary", {}),
        "research_profile": research_profile,
        "evidence_quality": evidence_quality,
        "backtest_evidence": data.get("backtest_evidence", {}),
        "ml_research": ml_research,
        "ml_prediction": ml_prediction,
        "ml_reference_trust": ml_reference_trust,
        "exit_signal": data.get("exit_signal"),
        "data_freshness": data.get("data_freshness"),
        "data_recovery": data.get("data_recovery")
        or (data.get("data_freshness") or {}).get("recovery"),
        "agent_outputs": data.get("agent_outputs", {}),
        "analyst_outputs": data.get("analyst_outputs", {}),
        "analyst_consensus": data.get("analyst_consensus", {}),
        "agentic_orchestration": data.get("agentic_orchestration", {}),
        "agentic_outputs": data.get("agentic_outputs", {}),
        "research_scope": data.get("research_scope", {}),
        "agent_summaries": {
            name: output.get("summary", {})
            for name, output in data.get("agent_outputs", {}).items()
        },
    }


def extract_news_events_summary(data: dict) -> dict | None:
    news_output = data.get("agent_outputs", {}).get("news", {})

    if "news_events_summary" in news_output:
        return news_output.get("news_events_summary")

    payload = news_output.get("payload", {})
    return payload.get("news_events_summary")


def default_news_analysis() -> dict:
    return {
        "summary": {
            "total_items": 0,
            "sentiment": "neutral",
            "high_importance_count": 0,
            "top_topics": {},
        }
    }


def default_fundamentals() -> dict:
    return {
        "status": "skipped",
        "summary": {
            "stance": "unknown",
            "positives": [],
            "risks": [],
        },
    }


def default_research_profile() -> dict:
    return {
        "technical_score": 0,
        "news_score": 0,
        "fundamental_score": 0,
        "risk_score": 0,
        "combined_score": 0,
        "setup_quality": "unknown",
        "risk_level": "unknown",
        "research_confidence": "low",
        "evidence_quality": default_evidence_quality(),
    }


def default_evidence_quality() -> dict:
    return {
        "level": "low",
        "stock_specific": "unknown",
        "peer_group": "not_used",
        "market_wide": "not_used",
        "data_completeness": "unknown",
        "signal_clarity": "unknown",
        "reason": "證據品質資料不足。",
    }
