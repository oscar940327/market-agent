import pandas as pd
import yfinance as yf


def fetch_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    return stock.history(period=period)


def fetch_price_data_range(
    ticker: str,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    return stock.history(start=start_date, end=end_date)
