from agent.agent_output import build_agent_output
from agent.research_profile import build_research_profile


def run_evidence_agent(
    *,
    technical: dict,
    signals: dict,
    news_analysis: dict,
    fundamentals: dict,
    price_history_rows: int | None = None,
    include_news: bool = True,
    include_fundamentals: bool = True,
    backtest_evidence: dict | None = None,
) -> dict:
    research_profile = build_research_profile(
        technical=technical,
        signals=signals,
        news_analysis=news_analysis,
        fundamentals=fundamentals,
        price_history_rows=price_history_rows,
        include_news=include_news,
        include_fundamentals=include_fundamentals,
        backtest_evidence=backtest_evidence,
    )
    evidence_quality = research_profile["evidence_quality"]

    return build_agent_output(
        agent="evidence",
        status="success",
        summary={
            "evidence_level": evidence_quality["level"],
            "research_confidence": research_profile["research_confidence"],
            "combined_score": research_profile["combined_score"],
            "risk_level": research_profile["risk_level"],
        },
        payload={
            "research_profile": research_profile,
            "evidence_quality": evidence_quality,
        },
        warnings=build_evidence_warnings(evidence_quality),
        metadata={
            "price_history_rows": price_history_rows,
            "peer_group": evidence_quality.get("peer_group"),
            "market_wide": evidence_quality.get("market_wide"),
        },
        fallback_used=False,
        legacy_fields={
            "research_profile": research_profile,
            "evidence_quality": evidence_quality,
        },
    )


def build_evidence_warnings(evidence_quality: dict) -> list[str]:
    warnings = []

    if evidence_quality.get("peer_group") == "not_used":
        warnings.append("peer_group_not_used")

    if evidence_quality.get("market_wide") == "not_used":
        warnings.append("market_wide_not_used")

    return warnings
