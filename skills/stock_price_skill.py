import pandas as pd

from data_providers.price_service import PriceFetchResult, fetch_recent_price_data


def get_recent_price_result(ticker: str, period: str = "6mo") -> PriceFetchResult:
    return fetch_recent_price_data(ticker=ticker, period=period)


# 抓 ticker 最近 6 months 股價資料
def get_recent_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    return get_recent_price_result(ticker=ticker, period=period).data
