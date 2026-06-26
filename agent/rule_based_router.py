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


def detect_intent(user_query: str) -> dict:
    query = user_query.lower()
    has_ticker = query_contains_ticker(user_query)

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

    if any(term in user_query or term in query for term in portfolio_terms):
        intent = "portfolio_analysis"
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
