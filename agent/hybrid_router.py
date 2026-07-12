import json
import os
import re

from agent.llm_analyst import OpenRouterChatClient
from agent.rule_based_router import KNOWN_TICKERS, detect_intent
from data.themes import THEMES


SUPPORTED_INTENTS = {
    "single_stock_analysis",
    "industry_trend",
    "backtest_query",
    "portfolio_analysis",
    "clarification_needed",
    "unsupported",
}
SUPPORTED_STRATEGIES = {"breakout", "volume_surge", "pullback"}
SUPPORTED_QUESTION_TYPES = {"entry_or_research", "holding_exit"}

ROUTER_SYSTEM_PROMPT = """
You classify market research questions. Return exactly one JSON object and no prose.
Allowed intents: single_stock_analysis, industry_trend, backtest_query,
portfolio_analysis, clarification_needed, unsupported.
Allowed strategies: breakout, volume_surge, pullback, or null.
Allowed question_type: entry_or_research or holding_exit.
Use a stock ticker only when it is explicit or unambiguous. Use a theme key only
from the supplied theme list. Never answer the investment question.
Schema:
{"intent":"...","ticker":null,"tickers":[],"theme":null,"strategy":null,
 "question_type":"entry_or_research","confidence":0.0,"reason":"short reason"}
""".strip()


def route_market_query(
    user_query: str,
    *,
    llm_client=None,
    mode: str | None = None,
    confidence_threshold: float | None = None,
) -> dict:
    rule_route = detect_intent(user_query)
    selected_mode = (mode or os.getenv("MARKET_AGENT_ROUTER_MODE", "hybrid")).lower()
    threshold = (
        _confidence_threshold_from_env()
        if confidence_threshold is None
        else confidence_threshold
    )
    if selected_mode == "rule_based" or (
        selected_mode != "llm" and rule_route["confidence"] >= threshold
    ):
        return rule_route

    client = llm_client if llm_client is not None else get_router_llm_client_from_env()
    if client is None:
        return _fallback_route(rule_route, "Router LLM is not configured.")

    try:
        raw = client.generate(
            ROUTER_SYSTEM_PROMPT,
            json.dumps(
                {
                    "question": user_query,
                    "rule_route": rule_route,
                    "supported_theme_keys": sorted(THEMES),
                },
                ensure_ascii=False,
            ),
        )
        llm_route = _validate_llm_route(_parse_json_object(raw), user_query)
    except (ValueError, RuntimeError, TypeError, json.JSONDecodeError) as error:
        return _fallback_route(rule_route, f"Router LLM fallback: {error}")

    return {
        **llm_route,
        "query": user_query,
        "has_ticker": bool(llm_route["ticker"] or llm_route["tickers"]),
        "router_used": "llm",
        "llm_used": True,
        "fallback_used": False,
        "rule_intent": rule_route["intent"],
        "rule_confidence": rule_route["confidence"],
        "matched_rule": rule_route["matched_rule"],
    }


def get_router_llm_client_from_env():
    if os.getenv("MARKET_AGENT_ROUTER_PROVIDER", "openrouter").lower() != "openrouter":
        return None
    client = OpenRouterChatClient.from_env()
    if client is None:
        return None
    router_model = os.getenv("MARKET_AGENT_ROUTER_MODEL", "").strip()
    if router_model:
        client.model = router_model
    return client


def _confidence_threshold_from_env() -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv("MARKET_AGENT_ROUTER_CONFIDENCE_THRESHOLD", "0.8"))))
    except ValueError:
        return 0.8


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Router response must be a JSON object.")
    return value


def _validate_llm_route(value: dict, user_query: str) -> dict:
    intent = value.get("intent")
    if intent not in SUPPORTED_INTENTS:
        raise ValueError("Router returned an unsupported intent.")

    ticker = _validate_ticker(value.get("ticker"))
    tickers = [_validate_ticker(item) for item in value.get("tickers", [])]
    tickers = list(dict.fromkeys(item for item in tickers if item))
    if ticker and ticker not in tickers:
        tickers.insert(0, ticker)

    theme = value.get("theme")
    if theme is not None and theme not in THEMES:
        raise ValueError("Router returned an unsupported theme.")
    strategy = value.get("strategy")
    if strategy is not None and strategy not in SUPPORTED_STRATEGIES:
        raise ValueError("Router returned an unsupported strategy.")
    question_type = value.get("question_type", "entry_or_research")
    if question_type not in SUPPORTED_QUESTION_TYPES:
        raise ValueError("Router returned an unsupported question type.")
    try:
        confidence = min(1.0, max(0.0, float(value.get("confidence", 0.5))))
    except (TypeError, ValueError) as error:
        raise ValueError("Router confidence must be numeric.") from error

    return {
        "intent": intent,
        "ticker": ticker,
        "tickers": tickers,
        "theme": theme,
        "strategy": strategy,
        "question_type": question_type,
        "confidence": confidence,
        "reason": str(value.get("reason") or "Classified by the router LLM."),
    }


def _validate_ticker(value) -> str | None:
    if value is None or value == "":
        return None
    ticker = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]{1,5}", ticker) or ticker not in KNOWN_TICKERS:
        raise ValueError(f"Unsupported ticker: {ticker}")
    return ticker


def _fallback_route(rule_route: dict, reason: str) -> dict:
    return {
        **rule_route,
        "router_used": "rule_based_fallback",
        "llm_used": False,
        "fallback_used": True,
        "fallback_reason": reason,
    }
