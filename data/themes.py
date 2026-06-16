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
        "tickers": [
            "NVDA",
            "AMD",
            "ADI",
            "AMAT",
            "ARM",
            "ASML",
            "AVGO",
            "INTC",
            "KLAC",
            "LRCX",
            "MCHP",
            "MPWR",
            "MRVL",
            "MU",
            "NXPI",
            "QCOM",
            "TXN",
            "TSM",
        ],
    },
    "mega_cap_tech": {
        "name": "大型科技股",
        "keywords": ["大型科技", "科技股", "mega cap", "big tech"],
        "tickers": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"],
    },
    "software_cloud": {
        "name": "軟體 / 雲端",
        "keywords": ["軟體", "雲端", "cloud", "software", "saas", "企業軟體"],
        "tickers": [
            "ADBE",
            "APP",
            "ADSK",
            "CDNS",
            "CTSH",
            "DDOG",
            "INTU",
            "MSFT",
            "MSTR",
            "PLTR",
            "ROP",
            "SNPS",
            "WDAY",
        ],
        "default_scan": False,
    },
    "cybersecurity": {
        "name": "資安",
        "keywords": ["資安", "cybersecurity", "security", "網路安全"],
        "tickers": ["CRWD", "FTNT", "PANW", "ZS"],
        "default_scan": False,
    },
    "internet_platforms": {
        "name": "網路平台 / 數位服務",
        "keywords": [
            "網路平台",
            "平台",
            "數位服務",
            "internet",
            "platform",
            "digital",
            "streaming",
        ],
        "tickers": [
            "GOOGL",
            "GOOG",
            "META",
            "AMZN",
            "NFLX",
            "PDD",
            "MELI",
            "SHOP",
            "DASH",
            "BKNG",
            "ABNB",
        ],
        "default_scan": False,
    },
    "consumer_discretionary": {
        "name": "非必需消費 / 電商零售",
        "keywords": ["非必需消費", "電商", "零售", "consumer discretionary", "retail"],
        "tickers": [
            "ABNB",
            "AMZN",
            "BKNG",
            "CPRT",
            "COST",
            "DASH",
            "EA",
            "MAR",
            "MELI",
            "NFLX",
            "ORLY",
            "PCAR",
            "ROST",
            "SBUX",
            "TTWO",
            "TSLA",
            "WBD",
            "WMT",
        ],
        "default_scan": False,
    },
    "consumer_staples": {
        "name": "民生消費",
        "keywords": ["民生消費", "必需消費", "consumer staples", "食品", "飲料"],
        "tickers": ["CCEP", "KDP", "KHC", "MDLZ", "MNST", "PEP", "COST", "WMT"],
        "default_scan": False,
    },
    "healthcare_biotech": {
        "name": "醫療 / 生技",
        "keywords": ["醫療", "生技", "healthcare", "health care", "biotech", "biotechnology"],
        "tickers": [
            "ALNY",
            "AMGN",
            "DXCM",
            "GEHC",
            "GILD",
            "IDXX",
            "INSM",
            "ISRG",
            "REGN",
            "VRTX",
        ],
        "default_scan": False,
    },
    "industrials_transport": {
        "name": "工業 / 運輸",
        "keywords": ["工業", "運輸", "industrial", "industrials", "transport", "logistics"],
        "tickers": [
            "ADP",
            "AXON",
            "CTAS",
            "CSX",
            "FAST",
            "FER",
            "HON",
            "ODFL",
            "PAYX",
            "PYPL",
            "VRSK",
        ],
        "default_scan": False,
    },
    "energy_utilities": {
        "name": "能源 / 公用事業",
        "keywords": ["能源", "石油", "公用事業", "energy", "oil", "utilities", "utility"],
        "tickers": ["AEP", "BKR", "CEG", "EXC", "FANG", "XEL"],
        "default_scan": False,
    },
    "telecom_media": {
        "name": "通訊 / 媒體",
        "keywords": ["通訊", "媒體", "telecom", "media", "broadband", "streaming"],
        "tickers": ["CHTR", "CMCSA", "CSCO", "TMUS", "WBD", "NFLX"],
        "default_scan": False,
    },
    "fintech_data_services": {
        "name": "金融科技 / 資料服務",
        "keywords": ["金融科技", "支付", "資料服務", "fintech", "payments", "data services"],
        "tickers": ["ADP", "INTU", "PAYX", "PYPL", "TRI", "VRSK"],
        "default_scan": False,
    },
    "auto_ev": {
        "name": "汽車 / 電動車",
        "keywords": ["汽車", "電動車", "車用", "auto", "ev", "automotive"],
        "tickers": ["TSLA", "PCAR", "ORLY", "CPRT"],
        "default_scan": False,
    },
    "hardware_networking": {
        "name": "硬體 / 網通",
        "keywords": ["硬體", "網通", "hardware", "networking", "optical", "devices"],
        "tickers": ["AAPL", "CSCO", "LITE", "WDC", "SNDK", "STX"],
        "default_scan": False,
    },
    "materials_chemicals": {
        "name": "材料 / 化工",
        "keywords": ["材料", "化工", "materials", "chemicals"],
        "tickers": ["LIN"],
        "default_scan": False,
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


def get_theme_scan_tickers(theme: dict) -> list[str]:
    tickers = theme["tickers"]
    scan_limit = theme.get("scan_limit")

    if scan_limit is None:
        return tickers

    return tickers[:scan_limit]


def get_all_theme_tickers(include_non_default: bool = False) -> list[str]:
    tickers = []

    for theme in THEMES.values():
        if not theme.get("default_scan", True) and not include_non_default:
            continue

        for ticker in theme["tickers"]:
            if ticker not in tickers:
                tickers.append(ticker)

    return tickers
