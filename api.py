from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent.analyst import (
    format_backtest_analysis,
    format_single_stock_analysis,
    format_theme_analysis,
)
from agent.rule_based_router import detect_intent
from main import run_backtest_query, run_single_stock_analysis, run_theme_analysis


app = FastAPI(
    title="Market Agent API",
    description="Personal stock research API backed by the Market Agent workflows.",
    version="0.1.0",
)


class RouteRequest(BaseModel):
    user_query: str = Field(..., min_length=1)


class SingleStockAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)
    include_news: bool = True


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    user_query: str = Field(..., min_length=1)


class ThemeAnalysisRequest(BaseModel):
    user_query: str = Field(..., min_length=1)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "market-agent",
    }


@app.post("/route")
def route_query(request: RouteRequest) -> dict:
    return detect_intent(request.user_query)


@app.post("/analyze/single")
def analyze_single_stock(request: SingleStockAnalysisRequest) -> dict:
    analysis_data = run_single_stock_analysis(
        ticker=normalize_ticker(request.ticker),
        user_query=request.user_query,
        include_news=request.include_news,
    )

    return {
        "data": analysis_data,
        "report": format_single_stock_analysis(analysis_data),
    }


@app.post("/backtest")
def backtest_strategy(request: BacktestRequest) -> dict:
    backtest_data = run_backtest_query(
        ticker=normalize_ticker(request.ticker),
        user_query=request.user_query,
    )

    return {
        "data": backtest_data,
        "report": format_backtest_analysis(backtest_data),
    }


@app.post("/themes")
def analyze_theme(request: ThemeAnalysisRequest) -> dict:
    theme_data = run_theme_analysis(request.user_query)

    return {
        "data": theme_data,
        "report": format_theme_analysis(theme_data),
    }
