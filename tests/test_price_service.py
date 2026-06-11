import pandas as pd

from data_providers import price_service
from data_providers.stooq_provider import build_stooq_symbol


def make_price_data():
    return pd.DataFrame(
        {
            "Close": [10, 11],
            "Volume": [1000, 1200],
        }
    )


def test_price_service_uses_first_successful_provider(monkeypatch):
    def fake_fetch_from_provider(provider, ticker, period):
        assert provider == "yfinance"
        assert ticker == "MU"
        assert period == "1y"
        return make_price_data()

    monkeypatch.setattr(price_service, "fetch_from_provider", fake_fetch_from_provider)

    result = price_service.fetch_recent_price_data(
        ticker="MU",
        period="1y",
        providers=("yfinance", "stooq"),
    )

    assert result.is_success is True
    assert result.provider == "yfinance"
    assert result.attempted_providers == ["yfinance"]
    assert result.errors == []


def test_price_service_falls_back_when_provider_returns_empty(monkeypatch):
    def fake_fetch_from_provider(provider, ticker, period):
        if provider == "yfinance":
            return pd.DataFrame()
        return make_price_data()

    monkeypatch.setattr(price_service, "fetch_from_provider", fake_fetch_from_provider)

    result = price_service.fetch_recent_price_data(
        ticker="MU",
        providers=("yfinance", "stooq"),
    )

    assert result.is_success is True
    assert result.provider == "stooq"
    assert result.attempted_providers == ["yfinance", "stooq"]
    assert result.errors == [
        {
            "provider": "yfinance",
            "message": "provider returned no price data",
        }
    ]


def test_price_service_falls_back_when_provider_raises(monkeypatch):
    def fake_fetch_from_provider(provider, ticker, period):
        if provider == "yfinance":
            raise RuntimeError("rate limited")
        return make_price_data()

    monkeypatch.setattr(price_service, "fetch_from_provider", fake_fetch_from_provider)

    result = price_service.fetch_recent_price_data(
        ticker="MU",
        providers=("yfinance", "stooq"),
    )

    assert result.is_success is True
    assert result.provider == "stooq"
    assert result.errors == [
        {
            "provider": "yfinance",
            "message": "rate limited",
        }
    ]


def test_price_service_returns_empty_result_when_all_providers_fail(monkeypatch):
    def fake_fetch_from_provider(provider, ticker, period):
        return pd.DataFrame()

    monkeypatch.setattr(price_service, "fetch_from_provider", fake_fetch_from_provider)

    result = price_service.fetch_recent_price_data(
        ticker="MU",
        providers=("yfinance", "stooq"),
    )

    assert result.is_success is False
    assert result.provider is None
    assert result.data.empty is True
    assert result.attempted_providers == ["yfinance", "stooq"]
    assert len(result.errors) == 2


def test_stooq_symbol_defaults_to_us_suffix():
    assert build_stooq_symbol("MU") == "mu.us"
    assert build_stooq_symbol("7203.jp") == "7203.jp"
