import inspect
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.analyst import format_error_message
from agent.hybrid_router import route_market_query
from agent.reporting import apply_required_report_sections, build_report
from agent.rule_based_router import (
    HISTORICAL_BACKTEST_TERMS,
    STRATEGY_TERMS,
    query_contains_any,
)
from data.themes import get_all_theme_tickers
from main import (
    run_backtest_query,
    run_portfolio_analysis,
    run_single_stock_analysis,
    run_theme_analysis,
)


KNOWN_TICKERS = {
    "AAPL",
    "AMD",
    "AMZN",
    "ASML",
    "AVGO",
    "DELL",
    "GOOGL",
    "META",
    "MSFT",
    "MU",
    "NVDA",
    "PLTR",
    "SMCI",
    "SNDK",
    "STX",
    "TSLA",
    "TSM",
    "WDC",
    *get_all_theme_tickers(include_non_default=True),
}

app = FastAPI(
    title="Market Agent API",
    description="Personal stock research API backed by the Market Agent workflows.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://oscar940327.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    user_query: str = Field(..., min_length=1)


class HoldingRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    market_value: float | None = None
    quantity: float | None = None
    cost_basis: float | None = None


class QueryRequest(BaseModel):
    user_query: str = Field(..., min_length=1)
    ticker: str | None = Field(default=None, max_length=12)
    holdings: list[HoldingRequest] | None = None
    include_news: bool = True
    include_fundamentals: bool = True
    include_technicals: bool = True
    analyst_mode: str = "rule_based"


class SingleStockAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)
    include_news: bool = True
    include_fundamentals: bool = True
    analyst_mode: str = "rule_based"


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)
    analyst_mode: str = "rule_based"


class ThemeAnalysisRequest(BaseModel):
    user_query: str = Field(..., min_length=1)
    analyst_mode: str = "rule_based"


class PortfolioAnalysisRequest(BaseModel):
    user_query: str = Field(
        default="我的投資組合目前有什麼需要注意？",
        min_length=1,
    )
    holdings: list[HoldingRequest] = Field(..., min_length=1)
    include_news: bool = False
    include_fundamentals: bool = False
    analyst_mode: str = "rule_based"


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def normalize_holdings_request(holdings: list[HoldingRequest]) -> list[dict]:
    return [
        {
            "ticker": normalize_ticker(holding.ticker),
            "market_value": holding.market_value,
            "quantity": holding.quantity,
            "cost_basis": holding.cost_basis,
        }
        for holding in holdings
    ]


def extract_ticker_from_query(user_query: str) -> str | None:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())

    for candidate in candidates:
        if candidate in KNOWN_TICKERS:
            return candidate

    return None


def get_explicit_request_fields(request: BaseModel) -> set[str]:
    if hasattr(request, "model_fields_set"):
        return set(request.model_fields_set)

    return set(getattr(request, "__fields_set__", set()))


def call_with_optional_hint(function, *, hint_name: str, hint_value, **kwargs):
    if hint_value is not None and hint_name in inspect.signature(function).parameters:
        kwargs[hint_name] = hint_value
    return function(**kwargs)


def should_use_research_workflow_for_backtest_query(request: QueryRequest) -> bool:
    query = request.user_query.lower()
    if query_contains_any(request.user_query, query, STRATEGY_TERMS) and query_contains_any(
        request.user_query,
        query,
        HISTORICAL_BACKTEST_TERMS,
    ):
        return False

    explicit_fields = get_explicit_request_fields(request)
    return (
        ("include_news" in explicit_fields and request.include_news)
        or (
            "include_fundamentals" in explicit_fields
            and request.include_fundamentals
        )
    )


def build_needs_ticker_result(intent: str, user_query: str) -> dict:
    return {
        "intent": intent,
        "status": "needs_ticker",
        "query": user_query,
        "message": "這類問題需要提供股票代號，請在 request body 加上 ticker。",
    }


def build_needs_holdings_result(intent: str, user_query: str) -> dict:
    return {
        "intent": intent,
        "status": "needs_holdings",
        "query": user_query,
        "message": "這類問題需要提供 holdings，例如 VOO、QQQM、TSLA 等持股清單。",
    }


def build_api_response(
    *,
    intent: str,
    data: dict,
    report: str,
    analyst: dict | None = None,
    route: dict | None = None,
) -> dict:
    status = data.get("status", "success")
    error = None

    if status != "success":
        error = {
            "status": status,
            "message": data.get("message", "分析無法完成。"),
        }

    response = {
        "status": status,
        "intent": intent,
        "data": data,
        "report": report,
        "error": error,
    }

    if analyst is not None:
        response["analyst"] = analyst

    if route is not None:
        response["route"] = route

    return response


def finalize_single_stock_report(
    *,
    analysis_data: dict,
    report: str,
    user_query: str,
) -> str:
    return apply_required_report_sections(
        kind="single_stock",
        data={**analysis_data, "query": user_query},
        report=report,
    )


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "market-agent",
    }


@app.post("/route")
def route_query(request: RouteRequest) -> dict:
    return route_market_query(request.user_query)


@app.post("/query")
def query_market_agent(request: QueryRequest) -> dict:
    route_result = route_market_query(request.user_query)
    intent = route_result["intent"]

    if (
        intent == "backtest_query"
        and should_use_research_workflow_for_backtest_query(request)
    ):
        route_result = {
            **route_result,
            "intent": "single_stock_analysis",
            "original_intent": "backtest_query",
            "reason": "research_options_requested",
        }
        intent = "single_stock_analysis"

    if intent == "single_stock_analysis":
        ticker = request.ticker or route_result.get("ticker") or extract_ticker_from_query(request.user_query)

        if not ticker:
            result = build_needs_ticker_result(intent, request.user_query)
            return build_api_response(
                intent=intent,
                route=route_result,
                data=result,
                report=format_error_message(result),
            )

        analysis_data = run_single_stock_analysis(
            ticker=normalize_ticker(ticker),
            user_query=request.user_query,
            include_news=request.include_news,
            include_fundamentals=request.include_fundamentals,
        )
        analysis_data["question_type"] = route_result.get("question_type", "entry_or_research")
        report_result = build_report(
            kind="single_stock",
            data=analysis_data,
            analyst_mode=request.analyst_mode,
        )
        report = finalize_single_stock_report(
            analysis_data=analysis_data,
            report=report_result["report"],
            user_query=request.user_query,
        )

        return build_api_response(
            intent=intent,
            route=route_result,
            data=analysis_data,
            report=report,
            analyst=report_result["analyst"],
        )

    if intent == "backtest_query":
        ticker = request.ticker or route_result.get("ticker") or extract_ticker_from_query(request.user_query)

        if not ticker:
            result = build_needs_ticker_result(intent, request.user_query)
            return build_api_response(
                intent=intent,
                route=route_result,
                data=result,
                report=format_error_message(result),
            )

        backtest_data = call_with_optional_hint(
            run_backtest_query,
            ticker=normalize_ticker(ticker),
            user_query=request.user_query,
            hint_name="strategy_hint",
            hint_value=route_result.get("strategy"),
        )
        report_result = build_report(
            kind="backtest",
            data=backtest_data,
            analyst_mode=request.analyst_mode,
        )

        return build_api_response(
            intent=intent,
            route=route_result,
            data=backtest_data,
            report=report_result["report"],
            analyst=report_result["analyst"],
        )

    if intent == "industry_trend":
        theme_data = call_with_optional_hint(
            run_theme_analysis,
            user_query=request.user_query,
            hint_name="theme_hint",
            hint_value=route_result.get("theme"),
        )
        report_result = build_report(
            kind="theme",
            data=theme_data,
            analyst_mode=request.analyst_mode,
        )

        return build_api_response(
            intent=intent,
            route=route_result,
            data=theme_data,
            report=report_result["report"],
            analyst=report_result["analyst"],
        )

    if intent == "portfolio_analysis":
        if not request.holdings:
            result = build_needs_holdings_result(intent, request.user_query)
            return build_api_response(
                intent=intent,
                route=route_result,
                data=result,
                report=format_error_message(result),
            )

        portfolio_data = run_portfolio_analysis(
            holdings=normalize_holdings_request(request.holdings),
            user_query=request.user_query,
            include_news=request.include_news,
            include_fundamentals=request.include_fundamentals,
        )
        report_result = build_report(
            kind="portfolio",
            data=portfolio_data,
            analyst_mode=request.analyst_mode,
        )

        return build_api_response(
            intent=intent,
            route=route_result,
            data=portfolio_data,
            report=report_result["report"],
            analyst=report_result["analyst"],
        )

    if intent == "clarification_needed":
        result = {
            "intent": intent,
            "status": "clarification_needed",
            "query": request.user_query,
            "message": route_result.get("reason") or "Please clarify the intended research target.",
        }
        return build_api_response(
            intent=intent,
            route=route_result,
            data=result,
            report=format_error_message(result),
        )

    result = {
        "intent": intent,
        "status": "unsupported_intent",
        "query": request.user_query,
        "message": "目前這個問題類型還沒有完整 workflow。",
    }

    return build_api_response(
        intent=intent,
        route=route_result,
        data=result,
        report=format_error_message(result),
    )


@app.post("/analyze/single")
def analyze_single_stock(request: SingleStockAnalysisRequest) -> dict:
    analysis_data = run_single_stock_analysis(
        ticker=normalize_ticker(request.ticker),
        user_query=request.user_query,
        include_news=request.include_news,
        include_fundamentals=request.include_fundamentals,
    )
    report_result = build_report(
        kind="single_stock",
        data=analysis_data,
        analyst_mode=request.analyst_mode,
    )
    report = finalize_single_stock_report(
        analysis_data=analysis_data,
        report=report_result["report"],
        user_query=request.user_query,
    )

    return build_api_response(
        intent="single_stock_analysis",
        data=analysis_data,
        report=report,
        analyst=report_result["analyst"],
    )


@app.post("/backtest")
def backtest_strategy(request: BacktestRequest) -> dict:
    backtest_data = run_backtest_query(
        ticker=normalize_ticker(request.ticker),
        user_query=request.user_query,
    )
    report_result = build_report(
        kind="backtest",
        data=backtest_data,
        analyst_mode=request.analyst_mode,
    )

    return build_api_response(
        intent="backtest_query",
        data=backtest_data,
        report=report_result["report"],
        analyst=report_result["analyst"],
    )


@app.post("/themes")
def analyze_theme(request: ThemeAnalysisRequest) -> dict:
    theme_data = run_theme_analysis(request.user_query)
    report_result = build_report(
        kind="theme",
        data=theme_data,
        analyst_mode=request.analyst_mode,
    )

    return build_api_response(
        intent="industry_trend",
        data=theme_data,
        report=report_result["report"],
        analyst=report_result["analyst"],
    )


@app.post("/portfolio")
def analyze_portfolio(request: PortfolioAnalysisRequest) -> dict:
    portfolio_data = run_portfolio_analysis(
        holdings=normalize_holdings_request(request.holdings),
        user_query=request.user_query,
        include_news=request.include_news,
        include_fundamentals=request.include_fundamentals,
    )
    report_result = build_report(
        kind="portfolio",
        data=portfolio_data,
        analyst_mode=request.analyst_mode,
    )

    return build_api_response(
        intent="portfolio_analysis",
        data=portfolio_data,
        report=report_result["report"],
        analyst=report_result["analyst"],
    )
