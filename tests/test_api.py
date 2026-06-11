import pytest
from pydantic import ValidationError

import api


def test_app_registers_public_api_paths():
    schema = api.app.openapi()

    assert "/health" in schema["paths"]
    assert "/route" in schema["paths"]
    assert "/analyze/single" in schema["paths"]
    assert "/backtest" in schema["paths"]
    assert "/themes" in schema["paths"]


def test_health_check():
    assert api.health_check() == {
        "status": "ok",
        "service": "market-agent",
    }


def test_route_endpoint_uses_rule_based_router():
    result = api.route_query(
        api.RouteRequest(user_query="突破策略以前表現怎麼樣？")
    )

    assert result["intent"] == "backtest_query"


def test_single_stock_endpoint_normalizes_ticker_and_returns_report(monkeypatch):
    captured = {}

    def fake_run_single_stock_analysis(ticker, user_query, include_news=True):
        captured["ticker"] = ticker
        captured["user_query"] = user_query
        captured["include_news"] = include_news
        return {
            "status": "no_price_data",
            "ticker": ticker,
            "message": "沒有取得股價資料",
        }

    monkeypatch.setattr(api, "run_single_stock_analysis", fake_run_single_stock_analysis)

    result = api.analyze_single_stock(
        api.SingleStockAnalysisRequest(
            ticker=" mu ",
            user_query="MU 現在適合進場嗎？",
            include_news=False,
        )
    )

    assert captured == {
        "ticker": "MU",
        "user_query": "MU 現在適合進場嗎？",
        "include_news": False,
    }
    assert result["data"]["ticker"] == "MU"
    assert "MU 分析無法完成" in result["report"]


def test_backtest_endpoint_returns_data_and_report(monkeypatch):
    def fake_run_backtest_query(ticker, user_query):
        return {
            "status": "unknown_strategy",
            "ticker": ticker,
            "strategy": "unknown",
            "user_query": user_query,
            "message": "請指定要回測的策略",
        }

    monkeypatch.setattr(api, "run_backtest_query", fake_run_backtest_query)

    result = api.backtest_strategy(
        api.BacktestRequest(
            ticker="mu",
            user_query="回測結果如何？",
        )
    )

    assert result["data"]["strategy"] == "unknown"
    assert "MU 分析無法完成" in result["report"]


def test_theme_endpoint_returns_data_and_report(monkeypatch):
    def fake_run_theme_analysis(user_query):
        return {
            "status": "success",
            "query": user_query,
            "theme_name": "測試主題",
            "results": [],
        }

    monkeypatch.setattr(api, "run_theme_analysis", fake_run_theme_analysis)

    result = api.analyze_theme(
        api.ThemeAnalysisRequest(user_query="AI server 相關股票有哪些值得觀察？")
    )

    assert result["data"]["theme_name"] == "測試主題"
    assert "測試主題 主題觀察清單" in result["report"]


def test_request_models_reject_missing_required_fields():
    with pytest.raises(ValidationError):
        api.SingleStockAnalysisRequest(ticker="MU")
