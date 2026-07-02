from agent.experts.backtest_agent import run_backtest_agent, select_backtest_strategy
from agent.experts.fundamental_agent import run_fundamental_agent
from agent.experts.news_agent import run_news_agent
from agent.experts.portfolio_agent import normalize_holdings, run_portfolio_agent
from agent.experts.technical_agent import run_technical_agent
from agent.exit_signal import build_exit_signal
from agent.research_profile import build_research_profile
from backtesting.evidence import REQUIRED_HISTORY_YEARS
from backtesting.signal_evidence import build_signal_backtest_evidence
from data_freshness import build_current_data_freshness
from daily_ml_predictions import (
    build_runtime_fallback_source,
    build_unavailable_source,
    convert_saved_prediction_to_ml_research,
    is_saved_prediction_usable,
)
from data_store import fetch_latest_ml_prediction
from ml_research import build_single_stock_ml_research
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


def has_triggered_strategy_signal(signals: dict) -> bool:
    return bool(
        signals.get("breakout", {}).get("is_breakout")
        or signals.get("volume_surge", {}).get("is_volume_surge")
        or signals.get("pullback", {}).get("is_pullback")
    )


def build_ml_research_for_single_stock(ticker: str, include_ml: bool = True) -> tuple[dict, dict | None]:
    if not include_ml:
        return (
            {
                "status": "skipped",
                "usage_policy": "reference_only",
                "reason": "ml_disabled_for_internal_workflow",
                "summary": "ML reference was skipped for this internal workflow.",
                "source": {"type": "skipped", "reason": "include_ml_false"},
            },
            None,
        )

    saved_prediction = safe_fetch_latest_ml_prediction(ticker=ticker)
    if is_saved_prediction_usable(saved_prediction):
        return convert_saved_prediction_to_ml_research(saved_prediction), saved_prediction

    fallback_reason = build_saved_prediction_fallback_reason(saved_prediction)
    runtime_ml_research = build_single_stock_ml_research(ticker=ticker)
    if runtime_ml_research.get("status") == "success":
        runtime_ml_research["source"] = build_runtime_fallback_source(
            reason=fallback_reason,
            saved_prediction=saved_prediction,
        )
    else:
        runtime_ml_research["source"] = build_unavailable_source(
            reason=fallback_reason,
            saved_prediction=saved_prediction,
        )
    return runtime_ml_research, saved_prediction


def safe_fetch_latest_ml_prediction(ticker: str) -> dict | None:
    try:
        return fetch_latest_ml_prediction(ticker=ticker)
    except Exception:
        return None


def build_saved_prediction_fallback_reason(saved_prediction: dict | None) -> str:
    if not saved_prediction:
        return "no_saved_daily_prediction"

    status = saved_prediction.get("prediction_status", "unknown")
    freshness = saved_prediction.get("prediction_freshness", "unknown")
    return f"saved_prediction_not_usable:{status}/{freshness}"


class MarketManagerAgent:
    def build_single_stock_plan(
        self,
        include_news: bool = True,
        include_fundamentals: bool = True,
    ) -> list[str]:
        plan = ["technical"]

        if include_news:
            plan.append("news")
        else:
            plan.append("news_skipped")

        if include_fundamentals:
            plan.append("fundamental")
        else:
            plan.append("fundamental_skipped")

        return plan

    def build_backtest_plan(self, user_query: str) -> list[str]:
        strategy = select_backtest_strategy(user_query)

        if strategy == "unknown":
            return ["backtest_strategy_selection"]

        return ["backtest_strategy_selection", "backtest"]

    def build_portfolio_plan(
        self,
        include_news: bool = False,
        include_fundamentals: bool = False,
    ) -> list[str]:
        plan = ["portfolio", "technical"]

        if include_news:
            plan.append("news")
        else:
            plan.append("news_skipped")

        if include_fundamentals:
            plan.append("fundamental")
        else:
            plan.append("fundamental_skipped")

        return plan

    def run_single_stock_analysis(
        self,
        ticker: str,
        user_query: str,
        include_news: bool = True,
        include_fundamentals: bool = True,
        include_ml: bool = True,
    ) -> dict:
        execution_plan = self.build_single_stock_plan(
            include_news=include_news,
            include_fundamentals=include_fundamentals,
        )
        price_data, fetch_error, price_source = fetch_price_data(ticker, period="1y")

        if fetch_error:
            return {
                "intent": "single_stock_analysis",
                "query": user_query,
                "execution_plan": execution_plan,
                **fetch_error,
            }

        data_error = validate_price_data(price_data, ticker=ticker, min_rows=50)

        if data_error:
            return {
                "intent": "single_stock_analysis",
                "query": user_query,
                "execution_plan": execution_plan,
                "price_source": price_source,
                **data_error,
            }

        technical_agent = run_technical_agent(price_data)
        backtest_evidence = {
            "status": "no_triggered_signals",
            "ticker": ticker,
            "signals": [],
            "summary": {
                "triggered_signal_count": 0,
                "message": "目前沒有明確突破、放量或回踩訊號，因此本次不附加歷史訊號參考。",
            },
        }

        if has_triggered_strategy_signal(technical_agent["signals"]):
            historical_price_data, history_fetch_error, history_price_source = (
                fetch_price_data(ticker, period="max")
            )

            if history_fetch_error:
                backtest_evidence = {
                    "status": history_fetch_error["status"],
                    "ticker": ticker,
                    "signals": [],
                    "summary": {
                        "triggered_signal_count": 0,
                        "message": history_fetch_error["message"],
                    },
                    "price_source": history_price_source,
                }
            else:
                historical_window_data, data_window = build_price_data_window(
                    historical_price_data
                )
                history_data_error = validate_price_data(
                    historical_window_data,
                    ticker=ticker,
                    min_rows=60,
                )

                if history_data_error:
                    backtest_evidence = {
                        "status": history_data_error["status"],
                        "ticker": ticker,
                        "signals": [],
                        "data_window": data_window,
                        "summary": {
                            "triggered_signal_count": 0,
                            "message": history_data_error["message"],
                        },
                        "price_source": history_price_source,
                    }
                else:
                    backtest_evidence = build_signal_backtest_evidence(
                        ticker=ticker,
                        price_data=historical_window_data,
                        current_signals=technical_agent["signals"],
                        data_window=data_window,
                    )
                    backtest_evidence["price_source"] = history_price_source

        news_agent = run_news_agent(ticker, include_news=include_news)
        fundamental_agent = run_fundamental_agent(
            ticker,
            include_fundamentals=include_fundamentals,
        )

        research_profile = build_research_profile(
            technical=technical_agent["technical_analysis"],
            signals=technical_agent["signals"],
            news_analysis=news_agent["news_analysis"],
            fundamentals=fundamental_agent["fundamentals"],
            price_history_rows=len(price_data),
            include_news=include_news,
            include_fundamentals=include_fundamentals,
            backtest_evidence=backtest_evidence,
        )
        ml_research, ml_prediction = build_ml_research_for_single_stock(
            ticker=ticker,
            include_ml=include_ml,
        )
        exit_signal = build_exit_signal(
            technical=technical_agent["technical_analysis"],
            signals=technical_agent["signals"],
            ml_research=ml_research,
        )
        data_freshness = build_current_data_freshness(ticker=ticker)

        return {
            "intent": "single_stock_analysis",
            "status": "success",
            "query": user_query,
            "ticker": ticker,
            "price_source": price_source,
            "execution_plan": execution_plan,
            "agent_outputs": {
                "technical": technical_agent,
                "news": news_agent,
                "fundamental": fundamental_agent,
                "backtest_evidence": backtest_evidence,
                "ml_research": ml_research,
                "exit_signal": {
                    "agent": "exit_signal",
                    "status": exit_signal["status"],
                    "summary": {
                        "exit_signal": exit_signal["exit_signal"],
                        "weakening_signal_20d": exit_signal["weakening_signal_20d"],
                        "email_alert_eligible": exit_signal["email_alert_eligible"],
                    },
                },
            },
            "technical_analysis": technical_agent["technical_analysis"],
            "signals": technical_agent["signals"],
            "backtest_evidence": backtest_evidence,
            "news": news_agent["news"],
            "news_analysis": news_agent["news_analysis"],
            "fundamentals": fundamental_agent["fundamentals"],
            "research_profile": research_profile,
            "evidence_quality": research_profile["evidence_quality"],
            "ml_research": ml_research,
            "ml_prediction": ml_prediction,
            "exit_signal": exit_signal,
            "data_freshness": data_freshness,
        }

    def run_backtest_query(self, ticker: str, user_query: str) -> dict:
        strategy = select_backtest_strategy(user_query)
        execution_plan = self.build_backtest_plan(user_query)

        if strategy == "unknown":
            return {
                "intent": "backtest_query",
                "ticker": ticker,
                "strategy": strategy,
                "user_query": user_query,
                "status": "unknown_strategy",
                "execution_plan": execution_plan,
                "message": "請指定要回測的策略：breakout、volume_surge 或 pullback。",
            }

        price_data, fetch_error, price_source = fetch_price_data(ticker, period="max")

        if fetch_error:
            return {
                "intent": "backtest_query",
                "strategy": strategy,
                "user_query": user_query,
                "execution_plan": execution_plan,
                **fetch_error,
            }

        backtest_price_data, data_window = build_price_data_window(price_data)

        data_error = validate_price_data(
            backtest_price_data,
            ticker=ticker,
            min_rows=60,
        )

        if data_error:
            return {
                "intent": "backtest_query",
                "strategy": strategy,
                "user_query": user_query,
                "execution_plan": execution_plan,
                "price_source": price_source,
                "data_window": data_window,
                **data_error,
            }

        backtest_agent = run_backtest_agent(
            ticker=ticker,
            user_query=user_query,
            price_data=backtest_price_data,
            data_window=data_window,
        )

        return {
            "intent": "backtest_query",
            "ticker": ticker,
            "strategy": strategy,
            "user_query": user_query,
            "status": backtest_agent["status"],
            "price_source": price_source,
            "data_start_date": data_window["data_start_date"],
            "data_end_date": data_window["data_end_date"],
            "data_as_of": data_window["data_as_of"],
            "data_window": data_window,
            "evidence_quality": backtest_agent["evidence_quality"],
            "execution_plan": execution_plan,
            "agent_outputs": {
                "backtest": backtest_agent,
            },
            "report": backtest_agent["report"],
        }

    def run_portfolio_analysis(
        self,
        holdings: list[dict],
        user_query: str,
        include_news: bool = False,
        include_fundamentals: bool = False,
    ) -> dict:
        execution_plan = self.build_portfolio_plan(
            include_news=include_news,
            include_fundamentals=include_fundamentals,
        )
        normalized_holdings = normalize_holdings(holdings)

        if not normalized_holdings:
            return {
                "intent": "portfolio_analysis",
                "status": "no_holdings",
                "query": user_query,
                "execution_plan": execution_plan,
                "message": "請提供至少一個有效持股 ticker。",
            }

        analyses = []

        for holding in normalized_holdings:
            analyses.append(
                self.run_single_stock_analysis(
                    ticker=holding["ticker"],
                    user_query=user_query,
                    include_news=include_news,
                    include_fundamentals=include_fundamentals,
                )
            )

        portfolio_agent = run_portfolio_agent(
            holdings=normalized_holdings,
            analyses=analyses,
        )

        return {
            "intent": "portfolio_analysis",
            "status": "success",
            "query": user_query,
            "execution_plan": execution_plan,
            "holdings": portfolio_agent["holdings"],
            "analyses": analyses,
            "agent_outputs": {
                "portfolio": portfolio_agent,
            },
            "portfolio": portfolio_agent,
            "portfolio_summary": portfolio_agent["summary"],
            "risk_summary": portfolio_agent["risk_summary"],
            "concentration": portfolio_agent["concentration"],
            "theme_exposure": portfolio_agent["theme_exposure"],
        }
