import re

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent.analyst import (
    format_backtest_analysis,
    format_error_message,
    format_single_stock_analysis,
    format_theme_analysis,
)
from agent.rule_based_router import detect_intent
from data.themes import get_all_theme_tickers
from main import run_backtest_query, run_single_stock_analysis, run_theme_analysis


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
    *get_all_theme_tickers(),
}

app = FastAPI(
    title="Market Agent API",
    description="Personal stock research API backed by the Market Agent workflows.",
    version="0.1.0",
)


class RouteRequest(BaseModel):
    user_query: str = Field(..., min_length=1)


class QueryRequest(BaseModel):
    user_query: str = Field(..., min_length=1)
    ticker: str | None = Field(default=None, max_length=12)
    include_news: bool = True
    include_fundamentals: bool = True


class SingleStockAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)
    include_news: bool = True
    include_fundamentals: bool = True


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)


class ThemeAnalysisRequest(BaseModel):
    user_query: str = Field(..., min_length=1)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def extract_ticker_from_query(user_query: str) -> str | None:
    candidates = re.findall(r"\b[A-Z]{1,5}\b", user_query.upper())

    for candidate in candidates:
        if candidate in KNOWN_TICKERS:
            return candidate

    return None


def build_needs_ticker_result(intent: str, user_query: str) -> dict:
    return {
        "intent": intent,
        "status": "needs_ticker",
        "query": user_query,
        "message": "這類問題需要提供股票代號，請在 request body 加上 ticker。",
    }


def build_api_response(
    *,
    intent: str,
    data: dict,
    report: str,
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

    if route is not None:
        response["route"] = route

    return response


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "market-agent",
    }


@app.post("/route")
def route_query(request: RouteRequest) -> dict:
    return detect_intent(request.user_query)


@app.post("/query")
def query_market_agent(request: QueryRequest) -> dict:
    route_result = detect_intent(request.user_query)
    intent = route_result["intent"]

    if intent == "single_stock_analysis":
        ticker = request.ticker or extract_ticker_from_query(request.user_query)

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

        return build_api_response(
            intent=intent,
            route=route_result,
            data=analysis_data,
            report=format_single_stock_analysis(analysis_data),
        )

    if intent == "backtest_query":
        ticker = request.ticker or extract_ticker_from_query(request.user_query)

        if not ticker:
            result = build_needs_ticker_result(intent, request.user_query)
            return build_api_response(
                intent=intent,
                route=route_result,
                data=result,
                report=format_error_message(result),
            )

        backtest_data = run_backtest_query(
            ticker=normalize_ticker(ticker),
            user_query=request.user_query,
        )

        return build_api_response(
            intent=intent,
            route=route_result,
            data=backtest_data,
            report=format_backtest_analysis(backtest_data),
        )

    if intent == "industry_trend":
        theme_data = run_theme_analysis(request.user_query)

        return build_api_response(
            intent=intent,
            route=route_result,
            data=theme_data,
            report=format_theme_analysis(theme_data),
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

    return build_api_response(
        intent="single_stock_analysis",
        data=analysis_data,
        report=format_single_stock_analysis(analysis_data),
    )


@app.post("/backtest")
def backtest_strategy(request: BacktestRequest) -> dict:
    backtest_data = run_backtest_query(
        ticker=normalize_ticker(request.ticker),
        user_query=request.user_query,
    )

    return build_api_response(
        intent="backtest_query",
        data=backtest_data,
        report=format_backtest_analysis(backtest_data),
    )


@app.post("/themes")
def analyze_theme(request: ThemeAnalysisRequest) -> dict:
    theme_data = run_theme_analysis(request.user_query)

    return build_api_response(
        intent="industry_trend",
        data=theme_data,
        report=format_theme_analysis(theme_data),
    )
