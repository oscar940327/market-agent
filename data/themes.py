THEMES = {
    "memory": {
        "name": "記憶體 / 儲存",
        "keywords": ["記憶體", "memory", "dram", "nand", "storage", "儲存"],
        "tickers": ["MU", "WDC", "STX", "SNDK"],
    },
    "ai_server": {
        "name": "AI server",
        "keywords": ["ai server", "ai伺服器", "ai 伺服器", "伺服器", "server"],
        "tickers": ["NVDA", "AMD", "AVGO", "SMCI", "DELL"],
    },
    "semiconductor": {
        "name": "半導體",
        "keywords": ["半導體", "semiconductor", "晶片", "chip"],
        "tickers": ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX"],
    },
    "mega_cap_tech": {
        "name": "大型科技股",
        "keywords": ["大型科技", "科技股", "mega cap", "big tech"],
        "tickers": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"],
    },
}


def find_theme_key(user_query: str):
    query = user_query.lower()

    for theme_key, theme in THEMES.items():
        if theme_key in query:
            return theme_key

        for keyword in theme["keywords"]:
            if keyword.lower() in query:
                return theme_key

    return None


def get_theme(theme_key: str):
    return THEMES.get(theme_key)


def list_theme_names() -> list[str]:
    return [theme["name"] for theme in THEMES.values()]


def get_all_theme_tickers() -> list[str]:
    tickers = []

    for theme in THEMES.values():
        for ticker in theme["tickers"]:
            if ticker not in tickers:
                tickers.append(ticker)

    return tickers
