import re

from data.themes import find_theme_key, get_all_theme_tickers


KNOWN_TICKERS = {
    "AAPL", "AMD", "AMZN", "ASML", "AVGO", "DELL", "GOOGL", "META",
    "MSFT", "MU", "NVDA", "PLTR", "SMCI", "SNDK", "STX", "TSLA",
    "TSM", "WDC", *get_all_theme_tickers(include_non_default=True),
}

SINGLE_STOCK_HOLDING_TERMS = (
    "持有", "已經持有", "減碼", "出場", "停損", "要不要賣", "要不要減",
    "要不要出", "already hold", "holding", "reduce", "exit", "sell",
)
STRATEGY_TERMS = ("突破", "放量", "拉回", "breakout", "volume surge", "pullback")
HISTORICAL_BACKTEST_TERMS = (
    "以前表現", "歷史表現", "過去表現", "以前", "歷史", "回測", "勝率",
    "表現怎麼樣", "backtest", "historical", "performance", "win rate",
)


def extract_known_tickers(user_query: str) -> list[str]:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())
    return list(dict.fromkeys(symbol for symbol in candidates if symbol in KNOWN_TICKERS))


def query_contains_ticker(user_query: str) -> bool:
    return bool(extract_known_tickers(user_query))


def count_known_tickers(user_query: str) -> int:
    return len(set(extract_known_tickers(user_query)))


def count_ticker_like_symbols(user_query: str) -> int:
    return len(set(re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())))


def query_contains_any(user_query: str, query: str, terms: tuple[str, ...]) -> bool:
    return any(term in user_query or term in query for term in terms)


def detect_strategy_hint(user_query: str) -> str | None:
    query = user_query.lower()
    if "breakout" in query or "突破" in user_query:
        return "breakout"
    if "volume surge" in query or "放量" in user_query:
        return "volume_surge"
    if "pullback" in query or "拉回" in user_query:
        return "pullback"
    return None


def detect_intent(user_query: str) -> dict:
    query = user_query.lower()
    known_tickers = extract_known_tickers(user_query)
    has_ticker = bool(known_tickers)
    known_ticker_count = len(known_tickers)
    ticker_like_count = count_ticker_like_symbols(user_query)
    portfolio_terms = ("投資組合", "持股", "部位", "觀察清單", "watchlist", "portfolio")
    backtest_terms = ("回測", "backtest", "勝率", "以前表現", "歷史表現")
    theme_terms = (
        "產業", "趨勢", "記憶體", "半導體", "類股", "概念股", "主題", "族群",
        "值得觀察", "哪些股票", "industry", "trend", "theme",
    )
    stock_research_terms = (
        "新聞", "news", "突破", "追高", "進場", "出場", "止損", "停損", "買", "賣", "適合",
    )
    has_holding_terms = query_contains_any(user_query, query, SINGLE_STOCK_HOLDING_TERMS)
    has_strategy_terms = query_contains_any(user_query, query, STRATEGY_TERMS)
    has_historical_terms = query_contains_any(user_query, query, HISTORICAL_BACKTEST_TERMS)
    has_portfolio_terms = query_contains_any(user_query, query, portfolio_terms)
    has_theme_terms = query_contains_any(user_query, query, theme_terms)

    if ticker_like_count >= 2 and has_holding_terms:
        intent, matched_rule = "portfolio_analysis", "multiple_tickers_with_holding_terms"
    elif known_ticker_count == 1 and has_holding_terms:
        intent, matched_rule = "single_stock_analysis", "single_ticker_with_holding_terms"
    elif has_portfolio_terms:
        intent, matched_rule = "portfolio_analysis", "portfolio_terms"
    elif has_strategy_terms and has_historical_terms:
        intent, matched_rule = "backtest_query", "strategy_with_historical_terms"
    elif query_contains_any(user_query, query, backtest_terms):
        intent, matched_rule = "backtest_query", "backtest_terms"
    elif has_ticker:
        intent, matched_rule = "single_stock_analysis", "known_ticker"
    elif has_theme_terms:
        intent, matched_rule = "industry_trend", "theme_terms"
    elif query_contains_any(user_query, query, stock_research_terms):
        intent, matched_rule = "single_stock_analysis", "stock_research_terms_without_ticker"
    elif any(char.isupper() for char in user_query):
        intent, matched_rule = "single_stock_analysis", "ticker_like_uppercase_text"
    else:
        intent, matched_rule = "unknown", "no_matching_rule"

    confidence, reason = _score_rule_confidence(
        intent, matched_rule, known_ticker_count, ticker_like_count,
        has_strategy_terms, has_historical_terms,
    )
    return {
        "intent": intent,
        "query": user_query,
        "has_ticker": has_ticker,
        "ticker": known_tickers[0] if len(known_tickers) == 1 else None,
        "tickers": known_tickers,
        "theme": find_theme_key(user_query),
        "strategy": detect_strategy_hint(user_query),
        "question_type": "holding_exit" if has_holding_terms and known_ticker_count <= 1 else "entry_or_research",
        "confidence": confidence,
        "reason": reason,
        "matched_rule": matched_rule,
        "router_used": "rule_based",
        "llm_used": False,
        "fallback_used": False,
    }


def _score_rule_confidence(
    intent: str,
    matched_rule: str,
    known_ticker_count: int,
    ticker_like_count: int,
    has_strategy_terms: bool,
    has_historical_terms: bool,
) -> tuple[float, str]:
    if intent == "unknown":
        return 0.2, "No reliable routing rule matched."
    if known_ticker_count >= 2 and matched_rule != "multiple_tickers_with_holding_terms":
        return 0.45, "Multiple tickers make the intended workflow ambiguous."
    if matched_rule == "ticker_like_uppercase_text" and known_ticker_count == 0:
        return 0.5, "Uppercase text resembles a ticker but is not in the supported universe."
    if matched_rule == "stock_research_terms_without_ticker":
        return 0.55, "A stock research request was found without a supported ticker."
    if intent == "backtest_query" and not (has_strategy_terms and has_historical_terms):
        return 0.7, "The query looks historical but the strategy is incomplete."
    high_confidence_rules = {
        "single_ticker_with_holding_terms", "multiple_tickers_with_holding_terms",
        "strategy_with_historical_terms", "known_ticker", "theme_terms", "portfolio_terms",
    }
    if matched_rule in high_confidence_rules:
        return 0.98, f"Matched explicit routing rule: {matched_rule}."
    return 0.8, f"Matched routing rule: {matched_rule}."
