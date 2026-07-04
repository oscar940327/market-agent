import re

from data.themes import get_all_theme_tickers


KNOWN_TICKERS = {
    "AAPL",
    "AMD",
    "AMZN",
    "ASML",
    "AVGO",
    "DELL",
    "GOOGL",
    "META",
    "MSFT",
    "MU",
    "NVDA",
    "PLTR",
    "SMCI",
    "SNDK",
    "STX",
    "TSLA",
    "TSM",
    "WDC",
    *get_all_theme_tickers(include_non_default=True),
}


def query_contains_ticker(user_query: str) -> bool:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())
    return any(candidate in KNOWN_TICKERS for candidate in candidates)


def count_known_tickers(user_query: str) -> int:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())
    return len({candidate for candidate in candidates if candidate in KNOWN_TICKERS})


def count_ticker_like_symbols(user_query: str) -> int:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())
    return len(set(candidates))


def query_contains_any(user_query: str, query: str, terms: tuple[str, ...]) -> bool:
    return any(term in user_query or term in query for term in terms)


SINGLE_STOCK_HOLDING_TERMS = (
    "持有",
    "已經持有",
    "減碼",
    "出場",
    "停損",
    "要不要賣",
    "要不要減",
    "要不要出",
    "already hold",
    "holding",
    "reduce",
    "exit",
    "sell",
)

STRATEGY_TERMS = (
    "突破",
    "放量",
    "拉回",
    "breakout",
    "volume surge",
    "pullback",
)

HISTORICAL_BACKTEST_TERMS = (
    "以前表現",
    "歷史表現",
    "過去表現",
    "以前",
    "歷史",
    "回測",
    "勝率",
    "表現怎麼樣",
    "backtest",
    "historical",
    "performance",
    "win rate",
)


def detect_intent(user_query: str) -> dict:
    query = user_query.lower()
    has_ticker = query_contains_ticker(user_query)
    known_ticker_count = count_known_tickers(user_query)
    ticker_like_count = count_ticker_like_symbols(user_query)

    portfolio_terms = (
        "投資組合",
        "持有",
        "持股",
        "部位",
        "觀察清單",
        "watchlist",
        "portfolio",
    )
    backtest_terms = (
        "回測",
        "backtest",
        "勝率",
        "以前表現",
        "歷史表現",
    )
    theme_terms = (
        "產業",
        "趨勢",
        "記憶體",
        "半導體",
        "類股",
        "概念股",
        "主題",
        "族群",
        "值得觀察",
        "哪些股票",
        "industry",
        "trend",
        "theme",
    )
    stock_research_terms = (
        "新聞",
        "news",
        "突破",
        "追高",
        "進場",
        "出場",
        "止損",
        "停損",
        "買",
        "賣",
        "適合",
    )

    if ticker_like_count >= 2 and query_contains_any(
        user_query,
        query,
        SINGLE_STOCK_HOLDING_TERMS,
    ):
        intent = "portfolio_analysis"
    elif known_ticker_count == 1 and query_contains_any(
        user_query,
        query,
        SINGLE_STOCK_HOLDING_TERMS,
    ):
        intent = "single_stock_analysis"
    elif any(term in user_query or term in query for term in portfolio_terms):
        intent = "portfolio_analysis"
    elif query_contains_any(user_query, query, STRATEGY_TERMS) and query_contains_any(
        user_query,
        query,
        HISTORICAL_BACKTEST_TERMS,
    ):
        intent = "backtest_query"
    elif any(term in user_query or term in query for term in backtest_terms):
        intent = "backtest_query"
    elif has_ticker:
        intent = "single_stock_analysis"
    elif any(term in user_query or term in query for term in theme_terms):
        intent = "industry_trend"
    elif any(term in user_query or term in query for term in stock_research_terms):
        intent = "single_stock_analysis"
    elif any(char.isupper() for char in user_query):
        intent = "single_stock_analysis"
    else:
        intent = "unknown"

    return {
        "intent": intent,
        "query": user_query,
        "has_ticker": has_ticker,
    }
