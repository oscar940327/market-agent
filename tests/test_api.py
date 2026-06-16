import pytest
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

import api


def test_app_registers_public_api_paths():
    schema = api.app.openapi()

    assert "/health" in schema["paths"]
    assert "/route" in schema["paths"]
    assert "/query" in schema["paths"]
    assert "/analyze/single" in schema["paths"]
    assert "/backtest" in schema["paths"]
    assert "/themes" in schema["paths"]
    assert "/portfolio" in schema["paths"]


def test_health_check():
    assert api.health_check() == {
        "status": "ok",
        "service": "market-agent",
    }


def test_app_allows_personal_website_origins():
    cors_middleware = [
        middleware
        for middleware in api.app.user_middleware
        if middleware.cls is CORSMiddleware
    ]

    assert len(cors_middleware) == 1
    assert "http://127.0.0.1:8001" in cors_middleware[0].kwargs["allow_origins"]
    assert "https://oscar940327.github.io" in cors_middleware[0].kwargs["allow_origins"]


def test_route_endpoint_uses_rule_based_router():
    result = api.route_query(
        api.RouteRequest(user_query="突破策略以前表現怎麼樣？")
    )

    assert result["intent"] == "backtest_query"


def test_extract_ticker_from_query_uses_known_ticker_symbols():
    assert api.extract_ticker_from_query("MU 現在適合進場嗎？") == "MU"
    assert api.extract_ticker_from_query("AI server 相關股票有哪些？") is None


def test_query_endpoint_dispatches_single_stock_with_ticker_from_query(monkeypatch):
    captured = {}

    def fake_run_single_stock_analysis(
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
    ):
        captured["ticker"] = ticker
        captured["user_query"] = user_query
        captured["include_news"] = include_news
        captured["include_fundamentals"] = include_fundamentals
        return {
            "status": "no_price_data",
            "ticker": ticker,
            "message": "沒有取得股價資料",
        }

    monkeypatch.setattr(api, "run_single_stock_analysis", fake_run_single_stock_analysis)

    result = api.query_market_agent(
        api.QueryRequest(
            user_query="MU 現在適合進場嗎？",
            include_news=False,
            include_fundamentals=False,
        )
    )

    assert captured == {
        "ticker": "MU",
        "user_query": "MU 現在適合進場嗎？",
        "include_news": False,
        "include_fundamentals": False,
    }
    assert result["status"] == "no_price_data"
    assert result["intent"] == "single_stock_analysis"
    assert result["error"] == {
        "status": "no_price_data",
        "message": "沒有取得股價資料",
    }
    assert result["route"]["intent"] == "single_stock_analysis"
    assert result["data"]["ticker"] == "MU"
    assert "MU 分析無法完成" in result["report"]


def test_query_endpoint_uses_explicit_ticker_for_backtest(monkeypatch):
    captured = {}

    def fake_run_backtest_query(ticker, user_query):
        captured["ticker"] = ticker
        captured["user_query"] = user_query
        return {
            "status": "unknown_strategy",
            "ticker": ticker,
            "strategy": "unknown",
            "user_query": user_query,
            "message": "請指定要回測的策略",
        }

    monkeypatch.setattr(api, "run_backtest_query", fake_run_backtest_query)

    result = api.query_market_agent(
        api.QueryRequest(
            ticker=" mu ",
            user_query="突破策略以前表現怎麼樣？",
        )
    )

    assert captured == {
        "ticker": "MU",
        "user_query": "突破策略以前表現怎麼樣？",
    }
    assert result["route"]["intent"] == "backtest_query"
    assert result["status"] == "unknown_strategy"
    assert result["intent"] == "backtest_query"
    assert result["error"]["status"] == "unknown_strategy"
    assert result["data"]["strategy"] == "unknown"


def test_query_endpoint_returns_needs_ticker_for_stock_workflow_without_ticker():
    result = api.query_market_agent(
        api.QueryRequest(user_query="突破可以進場嗎？")
    )

    assert result["route"]["intent"] == "single_stock_analysis"
    assert result["status"] == "needs_ticker"
    assert result["intent"] == "single_stock_analysis"
    assert result["error"]["status"] == "needs_ticker"
    assert result["data"]["status"] == "needs_ticker"
    assert "需要提供股票代號" in result["report"]


def test_query_endpoint_dispatches_theme_workflow(monkeypatch):
    def fake_run_theme_analysis(user_query):
        return {
            "status": "success",
            "query": user_query,
            "theme_name": "測試主題",
            "results": [],
        }

    monkeypatch.setattr(api, "run_theme_analysis", fake_run_theme_analysis)

    result = api.query_market_agent(
        api.QueryRequest(user_query="記憶體概念股有哪些值得觀察？")
    )

    assert result["route"]["intent"] == "industry_trend"
    assert result["status"] == "success"
    assert result["intent"] == "industry_trend"
    assert result["error"] is None
    assert result["data"]["theme_name"] == "測試主題"
    assert "測試主題 主題觀察清單" in result["report"]


def test_query_endpoint_returns_needs_holdings_for_portfolio_workflow():
    result = api.query_market_agent(
        api.QueryRequest(user_query="我目前持有 VOO QQQM 有什麼需要注意？")
    )

    assert result["route"]["intent"] == "portfolio_analysis"
    assert result["status"] == "needs_holdings"
    assert result["intent"] == "portfolio_analysis"
    assert result["error"]["status"] == "needs_holdings"
    assert "需要提供 holdings" in result["report"]


def test_query_endpoint_dispatches_portfolio_workflow(monkeypatch):
    captured = {}

    def fake_run_portfolio_analysis(
        holdings,
        user_query,
        include_news=False,
        include_fundamentals=False,
    ):
        captured["holdings"] = holdings
        captured["user_query"] = user_query
        captured["include_news"] = include_news
        captured["include_fundamentals"] = include_fundamentals
        return {
            "intent": "portfolio_analysis",
            "status": "success",
            "query": user_query,
            "portfolio": {
                "positions": [],
            },
            "portfolio_summary": {
                "holding_count": 2,
            },
            "risk_summary": {
                "risk_level": "low",
                "risk_factors": [],
            },
            "concentration": {
                "holding_count": 2,
                "largest_position": "VOO",
                "largest_weight": 0.5,
                "top_3_weight": 1.0,
                "position_concentration": "high",
            },
            "theme_exposure": {
                "exposure": {},
                "largest_theme": None,
                "largest_theme_weight": 0,
                "theme_concentration": "no_data",
            },
        }

    monkeypatch.setattr(api, "run_portfolio_analysis", fake_run_portfolio_analysis)

    result = api.query_market_agent(
        api.QueryRequest(
            user_query="我目前持有 VOO QQQM 有什麼需要注意？",
            holdings=[
                api.HoldingRequest(ticker="voo", market_value=1000),
                api.HoldingRequest(ticker="qqqm", market_value=1000),
            ],
            include_news=False,
            include_fundamentals=False,
        )
    )

    assert captured == {
        "holdings": [
            {
                "ticker": "VOO",
                "market_value": 1000.0,
                "quantity": None,
                "cost_basis": None,
            },
            {
                "ticker": "QQQM",
                "market_value": 1000.0,
                "quantity": None,
                "cost_basis": None,
            },
        ],
        "user_query": "我目前持有 VOO QQQM 有什麼需要注意？",
        "include_news": False,
        "include_fundamentals": False,
    }
    assert result["status"] == "success"
    assert result["intent"] == "portfolio_analysis"
    assert result["route"]["intent"] == "portfolio_analysis"
    assert "投資組合研究摘要" in result["report"]


def test_build_api_response_has_stable_success_shape():
    result = api.build_api_response(
        intent="industry_trend",
        data={"status": "success", "value": 1},
        report="ok",
    )

    assert result == {
        "status": "success",
        "intent": "industry_trend",
        "data": {"status": "success", "value": 1},
        "report": "ok",
        "error": None,
    }


def test_build_api_response_has_stable_error_shape():
    result = api.build_api_response(
        intent="single_stock_analysis",
        data={"status": "needs_ticker", "message": "missing ticker"},
        report="error report",
    )

    assert result["status"] == "needs_ticker"
    assert result["intent"] == "single_stock_analysis"
    assert result["error"] == {
        "status": "needs_ticker",
        "message": "missing ticker",
    }


def test_single_stock_endpoint_normalizes_ticker_and_returns_report(monkeypatch):
    captured = {}

    def fake_run_single_stock_analysis(
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
    ):
        captured["ticker"] = ticker
        captured["user_query"] = user_query
        captured["include_news"] = include_news
        captured["include_fundamentals"] = include_fundamentals
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
            include_fundamentals=False,
        )
    )

    assert captured == {
        "ticker": "MU",
        "user_query": "MU 現在適合進場嗎？",
        "include_news": False,
        "include_fundamentals": False,
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
