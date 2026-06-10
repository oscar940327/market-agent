# 最簡易的 agent

def detect_intent(user_query: str) -> dict:
    query = user_query.lower()

    known_tickers = ["mu", "nvda", "tsla", "pltr", "sndk", "amd", "aapl", "msft"]

    if (
        "回測" in user_query
        or "backtest" in query
        or "勝率" in user_query
        or "以前表現" in user_query
        or "歷史表現" in user_query
    ):
        intent = "backtest_query"
    elif any(ticker in query.split() for ticker in known_tickers):
        intent = "single_stock_analysis"
    elif (
        "新聞" in user_query
        or "news" in query
        or "突破" in user_query
        or "追高" in user_query
        or "進場" in user_query
    ):
        intent = "single_stock_analysis"
    elif (
        "產業" in user_query
        or "趨勢" in user_query
        or "記憶體" in user_query
        or "半導體" in user_query
        or "industry" in query
        or "trend" in query
    ):
        intent = "industry_trend"
    elif any(char.isupper() for char in user_query):
        intent = "single_stock_analysis"
    else:
        intent = "unknown"

    return {
        "intent": intent,
        "query": user_query,
    }