import yfinance as yf


FUNDAMENTAL_FIELDS = {
    "market_cap": "marketCap",
    "trailing_pe": "trailingPE",
    "forward_pe": "forwardPE",
    "price_to_sales": "priceToSalesTrailing12Months",
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    "gross_margins": "grossMargins",
    "operating_margins": "operatingMargins",
    "profit_margins": "profitMargins",
    "free_cashflow": "freeCashflow",
    "debt_to_equity": "debtToEquity",
    "earnings_date": "earningsDate",
    "sector": "sector",
    "industry": "industry",
}


def get_basic_fundamentals(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info = stock.info or {}

    metrics = {
        output_key: normalize_value(info.get(source_key))
        for output_key, source_key in FUNDAMENTAL_FIELDS.items()
    }

    return {
        "status": "success",
        "provider": "yfinance",
        "metrics": metrics,
        "summary": summarize_fundamentals(metrics),
    }


def normalize_value(value):
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def summarize_fundamentals(metrics: dict) -> dict:
    positives = []
    risks = []

    revenue_growth = metrics.get("revenue_growth")
    earnings_growth = metrics.get("earnings_growth")
    gross_margins = metrics.get("gross_margins")
    debt_to_equity = metrics.get("debt_to_equity")
    trailing_pe = metrics.get("trailing_pe")

    if isinstance(revenue_growth, (int, float)):
        if revenue_growth > 0:
            positives.append("營收成長為正")
        elif revenue_growth < 0:
            risks.append("營收成長為負")

    if isinstance(earnings_growth, (int, float)):
        if earnings_growth > 0:
            positives.append("獲利成長為正")
        elif earnings_growth < 0:
            risks.append("獲利成長為負")

    if isinstance(gross_margins, (int, float)) and gross_margins >= 0.4:
        positives.append("毛利率相對較高")

    if isinstance(debt_to_equity, (int, float)) and debt_to_equity >= 150:
        risks.append("負債權益比偏高")

    if isinstance(trailing_pe, (int, float)) and trailing_pe >= 60:
        risks.append("本益比偏高")

    if not positives and not risks:
        stance = "neutral"
    elif positives and not risks:
        stance = "positive"
    elif risks and not positives:
        stance = "negative"
    else:
        stance = "mixed"

    return {
        "stance": stance,
        "positives": positives,
        "risks": risks,
    }
