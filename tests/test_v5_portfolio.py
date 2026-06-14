import api
from agent.experts.portfolio_agent import (
    calculate_concentration,
    calculate_theme_exposure,
    normalize_holdings,
    run_portfolio_agent,
)
from agent.llm_analyst import build_llm_user_prompt
from agent.market_manager import MarketManagerAgent
from agent.reporting import build_report
from agent.rule_based_router import detect_intent


def make_stock_analysis(ticker: str, trend: str = "strong") -> dict:
    is_above_ma20 = trend != "weak"

    return {
        "intent": "single_stock_analysis",
        "status": "success",
        "query": "我的投資組合目前有什麼需要注意？",
        "ticker": ticker,
        "technical_analysis": {
            "current_price": 100,
            "ma10": 95,
            "ma20": 90,
            "ma50": 80,
            "is_above_ma20": is_above_ma20,
            "short_term_trend": trend,
        },
        "signals": {
            "breakout": {"is_breakout": False},
            "volume_surge": {"is_volume_surge": False},
            "pullback": {"is_pullback": False},
        },
        "news": [],
        "news_analysis": {"summary": {"sentiment": "neutral"}},
        "fundamentals": {
            "status": "skipped",
            "summary": {
                "stance": "unknown",
                "positives": [],
                "risks": [],
            },
        },
        "research_profile": {
            "setup_quality": "neutral_positive",
            "risk_level": "low",
        },
    }


def test_normalize_holdings_uses_market_value_weights():
    holdings = normalize_holdings(
        [
            {"ticker": " voo ", "market_value": 6000},
            {"ticker": "qqqm", "market_value": 3000},
            {"ticker": "tsla", "market_value": 1000},
        ]
    )

    assert [holding["ticker"] for holding in holdings] == ["VOO", "QQQM", "TSLA"]
    assert [holding["weight"] for holding in holdings] == [0.6, 0.3, 0.1]


def test_portfolio_agent_calculates_concentration_and_theme_exposure():
    holdings = normalize_holdings(
        [
            {"ticker": "NVDA", "market_value": 5000},
            {"ticker": "AMD", "market_value": 3000},
            {"ticker": "TSM", "market_value": 2000},
        ]
    )

    concentration = calculate_concentration(holdings)
    theme_exposure = calculate_theme_exposure(holdings)

    assert concentration["largest_position"] == "NVDA"
    assert concentration["position_concentration"] == "high"
    assert theme_exposure["largest_theme"] in {"ai_server", "semiconductor"}
    assert theme_exposure["theme_concentration"] in {"medium", "high"}


def test_market_manager_runs_portfolio_workflow(monkeypatch):
    captured_tickers = []

    def fake_run_single_stock_analysis(
        self,
        ticker,
        user_query,
        include_news=True,
        include_fundamentals=True,
    ):
        captured_tickers.append(ticker)
        return make_stock_analysis(ticker)

    monkeypatch.setattr(
        MarketManagerAgent,
        "run_single_stock_analysis",
        fake_run_single_stock_analysis,
    )

    result = MarketManagerAgent().run_portfolio_analysis(
        holdings=[{"ticker": "VOO"}, {"ticker": "QQQM"}, {"ticker": "PLTR"}],
        user_query="我目前持有 VOO QQQM PLTR 有什麼需要注意？",
        include_news=False,
        include_fundamentals=False,
    )

    assert result["status"] == "success"
    assert result["intent"] == "portfolio_analysis"
    assert result["execution_plan"] == [
        "portfolio",
        "technical",
        "news_skipped",
        "fundamental_skipped",
    ]
    assert captured_tickers == ["VOO", "QQQM", "PLTR"]
    assert result["agent_outputs"]["portfolio"]["agent"] == "portfolio"
    assert result["portfolio_summary"]["holding_count"] == 3


def test_portfolio_report_and_llm_payload_include_risk_summary():
    data = {
        "intent": "portfolio_analysis",
        "status": "success",
        "query": "我的投資組合目前有什麼需要注意？",
        "execution_plan": ["portfolio", "technical", "news_skipped"],
        "holdings": normalize_holdings([{"ticker": "NVDA"}, {"ticker": "AMD"}]),
    }
    portfolio = run_portfolio_agent(
        holdings=data["holdings"],
        analyses=[make_stock_analysis("NVDA"), make_stock_analysis("AMD", "weak")],
    )
    data.update(
        {
            "portfolio": portfolio,
            "portfolio_summary": portfolio["summary"],
            "risk_summary": portfolio["risk_summary"],
            "concentration": portfolio["concentration"],
            "theme_exposure": portfolio["theme_exposure"],
        }
    )

    report = build_report(kind="portfolio", data=data, analyst_mode="rule_based")
    prompt = build_llm_user_prompt(kind="portfolio", data=data)

    assert "投資組合研究摘要" in report["report"]
    assert "Portfolio Risk" in report["report"]
    assert '"kind": "portfolio"' in prompt
    assert '"risk_summary"' in prompt


def test_api_portfolio_endpoint_returns_report(monkeypatch):
    def fake_run_portfolio_analysis(
        holdings,
        user_query,
        include_news=False,
        include_fundamentals=False,
    ):
        portfolio = run_portfolio_agent(
            holdings=holdings,
            analyses=[make_stock_analysis(holding["ticker"]) for holding in holdings],
        )
        return {
            "intent": "portfolio_analysis",
            "status": "success",
            "query": user_query,
            "execution_plan": ["portfolio", "technical", "news_skipped"],
            "holdings": portfolio["holdings"],
            "portfolio": portfolio,
            "portfolio_summary": portfolio["summary"],
            "risk_summary": portfolio["risk_summary"],
            "concentration": portfolio["concentration"],
            "theme_exposure": portfolio["theme_exposure"],
        }

    monkeypatch.setattr(api, "run_portfolio_analysis", fake_run_portfolio_analysis)

    result = api.analyze_portfolio(
        api.PortfolioAnalysisRequest(
            user_query="我目前持有 VOO QQQM TSLA 有什麼需要注意？",
            holdings=[
                api.HoldingRequest(ticker="VOO", market_value=5000),
                api.HoldingRequest(ticker="QQQM", market_value=3000),
                api.HoldingRequest(ticker="TSLA", market_value=2000),
            ],
        )
    )

    assert result["status"] == "success"
    assert result["intent"] == "portfolio_analysis"
    assert result["analyst"]["mode_used"] == "rule_based"
    assert result["data"]["portfolio_summary"]["holding_count"] == 3
    assert "投資組合研究摘要" in result["report"]


def test_router_detects_portfolio_questions_first():
    result = detect_intent("我目前持有 VOO QQQM TSLA 有什麼需要注意？")

    assert result["intent"] == "portfolio_analysis"
