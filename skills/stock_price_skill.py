# 負責抓資料

import yfinance as yf
import pandas as pd

# 抓 ticker 最近 6 monthes 股價資料
def get_recent_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    price_data = stock.history(period=period)

    return price_data