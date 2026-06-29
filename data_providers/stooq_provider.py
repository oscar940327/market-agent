from datetime import date, timedelta
from io import StringIO
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


PERIOD_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
    "5y": 1830,
    "15y": 5479,
    "max": 36525,
}


def build_stooq_symbol(ticker: str) -> str:
    normalized = ticker.strip().lower()

    if "." in normalized:
        return normalized

    return f"{normalized}.us"


def build_start_date(period: str) -> str:
    days = PERIOD_DAYS.get(period, PERIOD_DAYS["6mo"])
    start_date = date.today() - timedelta(days=days)
    return start_date.strftime("%Y%m%d")


def fetch_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    params = urlencode(
        {
            "s": build_stooq_symbol(ticker),
            "i": "d",
            "d1": build_start_date(period),
        }
    )
    url = f"https://stooq.com/q/d/l/?{params}"

    with urlopen(url, timeout=10) as response:
        csv_data = response.read().decode("utf-8")

    data = pd.read_csv(StringIO(csv_data))

    if data.empty or "Date" not in data.columns:
        return pd.DataFrame()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.set_index("Date")
    data = data.sort_index()

    expected_columns = ["Open", "High", "Low", "Close", "Volume"]
    available_columns = [column for column in expected_columns if column in data.columns]

    return data[available_columns]


def fetch_price_data_range(
    ticker: str,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    params = {
        "s": build_stooq_symbol(ticker),
        "i": "d",
        "d1": start_date.replace("-", ""),
    }
    if end_date:
        params["d2"] = end_date.replace("-", "")

    url = f"https://stooq.com/q/d/l/?{urlencode(params)}"

    with urlopen(url, timeout=10) as response:
        csv_data = response.read().decode("utf-8")

    data = pd.read_csv(StringIO(csv_data))

    if data.empty or "Date" not in data.columns:
        return pd.DataFrame()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.set_index("Date")
    data = data.sort_index()

    expected_columns = ["Open", "High", "Low", "Close", "Volume"]
    available_columns = [column for column in expected_columns if column in data.columns]

    return data[available_columns]
