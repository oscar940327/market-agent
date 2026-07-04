from agent.agent_output import build_agent_output
from backtesting.evidence import REQUIRED_HISTORY_YEARS
from skills.stock_price_skill import get_recent_price_result


def validate_price_data(price_data, ticker: str, min_rows: int):
    if price_data is None or price_data.empty:
        return {
            "ticker": ticker,
            "status": "no_price_data",
            "message": "沒有取得股價資料，請確認股票代號是否正確或稍後再試。",
        }

    missing_columns = [
        column for column in ["Close", "Volume"] if column not in price_data.columns
    ]

    if missing_columns:
        return {
            "ticker": ticker,
            "status": "invalid_price_data",
            "message": f"股價資料缺少必要欄位：{', '.join(missing_columns)}。",
        }

    if len(price_data) < min_rows:
        return {
            "ticker": ticker,
            "status": "not_enough_price_data",
            "message": f"目前只有 {len(price_data)} 筆資料，至少需要 {min_rows} 筆。",
        }

    return None


def fetch_price_data(ticker: str, period: str):
    try:
        price_result = get_recent_price_result(ticker, period=period)
    except Exception as error:
        return None, {
            "ticker": ticker,
            "status": "price_data_error",
            "message": f"取得股價資料時發生錯誤：{error}",
            "price_source": {
                "provider": None,
                "attempted_providers": [],
                "errors": [{"provider": "price_service", "message": str(error)}],
            },
        }, None

    price_source = {
        "provider": price_result.provider,
        "attempted_providers": price_result.attempted_providers,
        "errors": price_result.errors,
    }

    return price_result.data, None, price_source


def build_price_data_window(price_data, required_years: int = REQUIRED_HISTORY_YEARS):
    sorted_data = price_data.sort_index()
    latest_date = sorted_data.index.max()
    target_start_date = latest_date - required_years_to_offset(required_years)
    window_data = sorted_data.loc[sorted_data.index >= target_start_date]

    if window_data.empty:
        window_data = sorted_data

    data_start = window_data.index.min()
    data_end = window_data.index.max()
    history_years = (data_end - data_start).days / 365.25
    has_required_history = data_start <= target_start_date + required_history_tolerance()

    return window_data, {
        "data_start_date": data_start.date().isoformat(),
        "data_end_date": data_end.date().isoformat(),
        "data_as_of": data_end.date().isoformat(),
        "target_start_date": target_start_date.date().isoformat(),
        "history_years": round(history_years, 2),
        "required_history_years": required_years,
        "has_required_history": bool(has_required_history),
    }


def required_years_to_offset(years: int):
    import pandas as pd

    return pd.DateOffset(years=years)


def required_history_tolerance():
    import pandas as pd

    # The target date may fall on a weekend or holiday, so allow a few calendar days.
    return pd.Timedelta(days=7)


def build_market_data_agent_output(
    *,
    ticker: str,
    period: str,
    price_data=None,
    price_source: dict | None = None,
    error: dict | None = None,
    data_window: dict | None = None,
) -> dict:
    if error:
        status = map_price_error_status(error.get("status"))
        summary = error.get("message", "Price data is unavailable.")
        warnings = [summary] if status != "failed" else []
        errors = [summary] if status == "failed" else []
    else:
        status = "success"
        rows = 0 if price_data is None else len(price_data)
        summary = f"Fetched {rows} price rows for {ticker}."
        warnings = []
        errors = []

    return build_agent_output(
        agent="market_data",
        status=status,
        summary=summary,
        payload={
            "ticker": ticker,
            "period": period,
            "price_data": price_data,
            "price_source": price_source,
            "error": error,
            "data_window": data_window,
        },
        warnings=warnings,
        errors=errors,
        metadata={
            "ticker": ticker,
            "period": period,
            "provider": (price_source or {}).get("provider"),
            "data_window": data_window,
        },
        fallback_used=False,
    )


def map_price_error_status(status: str | None) -> str:
    if status in {"no_price_data", "invalid_price_data", "not_enough_price_data"}:
        return "unavailable"
    if status == "price_data_error":
        return "failed"

    return "partial_success"
