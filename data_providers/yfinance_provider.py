import pandas as pd
import yfinance as yf


def fetch_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    return stock.history(period=period)
