def detect_intent(user_query: str) -> dict:
    query = user_query.lower()

    if "回測" in user_query or "backtest" in query:
        intent = "backtest_query"
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