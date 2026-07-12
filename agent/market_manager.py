from agent.agent_output import build_agent_output, wrap_legacy_agent_output
from agent.analyst_outputs import build_analyst_consensus, build_single_stock_analyst_outputs
from agent.experts.backtest_agent import run_backtest_agent, select_backtest_strategy
from agent.experts.fundamental_agent import run_fundamental_agent
from agent.experts.news_agent import run_news_agent
from agent.experts.portfolio_agent import normalize_holdings, run_portfolio_agent
from agent.experts.technical_agent import run_technical_agent
from agent.exit_signal import build_exit_signal
from agent.evidence_agent import run_evidence_agent
from agent.market_data_agent import (
    build_market_data_agent_output,
    build_price_data_window,
    fetch_price_data,
    validate_price_data,
)
from agent.ml_research_agent import (
    build_ml_research_agent_output,
    build_ml_research_for_single_stock as run_ml_research_agent,
    build_saved_prediction_fallback_reason,
    safe_fetch_latest_ml_prediction,
)
from agent.ml_reference_trust import build_ml_reference_trust
from agent.orchestration_policy import build_single_stock_orchestration_summary
from backtesting.signal_evidence import build_signal_backtest_evidence
from data_freshness import build_current_data_freshness
from ml_model_improvement import (
    apply_downside_risk_overlay,
    build_current_downside_feature_snapshot,
)
from ml_research import build_single_stock_ml_research


def has_triggered_strategy_signal(signals: dict) -> bool:
    return bool(
        signals.get("breakout", {}).get("is_breakout")
        or signals.get("volume_surge", {}).get("is_volume_surge")
        or signals.get("pullback", {}).get("is_pullback")
    )


def build_ml_research_for_single_stock(ticker: str, include_ml: bool = True) -> tuple[dict, dict | None]:
    return run_ml_research_agent(
        ticker=ticker,
        include_ml=include_ml,
        fetch_prediction=safe_fetch_latest_ml_prediction,
        runtime_builder=build_single_stock_ml_research,
    )


def map_backtest_evidence_status(backtest_evidence: dict) -> str:
    status = backtest_evidence.get("status", "success")

    if status == "success":
        return "success"
    if status == "no_triggered_signals":
        return "skipped"
    if status in {"no_price_data", "invalid_price_data", "not_enough_price_data"}:
        return "unavailable"
    if status == "price_data_error":
        return "failed"

    return "partial_success"


def build_backtest_evidence_warnings(backtest_evidence: dict) -> list[str]:
    status = backtest_evidence.get("status")
    if status in {None, "success"}:
        return []

    message = (backtest_evidence.get("summary") or {}).get("message")
    if message:
        return [message]

    return [f"backtest_evidence_status:{status}"]


def build_backtest_data_freshness(data_window: dict) -> dict:
    data_as_of = data_window.get("data_as_of") or data_window.get("data_end_date")
    return {
        "overall": "fresh",
        "source": "backtest_price_window",
        "latest_date": data_as_of,
        "data_as_of": data_as_of,
        "message": f"回測使用截至 {data_as_of or 'unknown'} 的歷史價格資料。",
        "warnings": [],
    }


def build_backtest_ml_reference() -> dict:
    return {
        "status": "skipped",
        "source": {
            "type": "not_applicable",
            "reason": "backtest_query_uses_historical_strategy_results",
        },
        "message": "策略回測問題使用歷史交易結果，不使用 ML Reference。",
        "targets": {
            "up_5d": {},
            "up_10d": {},
            "up_20d": {},
            "large_drop_20d": {},
        },
        "return_reference": {},
        "return_model": {
            "targets": {
                "forward_return_5d": {},
                "forward_return_10d": {},
                "forward_return_20d": {},
                "max_drop_20d": {},
            }
        },
    }


def map_exit_signal_status(exit_signal: dict) -> str:
    status = exit_signal.get("status", "unavailable")
    if status in {"success", "skipped", "unavailable", "failed"}:
        return status

    return "partial_success"


def build_exit_signal_warnings(exit_signal: dict) -> list[str]:
    if exit_signal.get("status") == "success":
        return []

    reason = exit_signal.get("reason") or exit_signal.get("status", "unknown")
    return [str(reason)]


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
        market_data_agent = build_market_data_agent_output(
            ticker=ticker,
            period="1y",
            price_data=price_data,
            price_source=price_source,
            error=fetch_error,
        )

        if fetch_error:
            return {
                "intent": "single_stock_analysis",
                "query": user_query,
                "execution_plan": execution_plan,
                **fetch_error,
            }

        data_error = validate_price_data(price_data, ticker=ticker, min_rows=50)

        if data_error:
            market_data_agent = build_market_data_agent_output(
                ticker=ticker,
                period="1y",
                price_data=price_data,
                price_source=price_source,
                error=data_error,
            )
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
            historical_market_data_agent = build_market_data_agent_output(
                ticker=ticker,
                period="max",
                price_data=historical_price_data,
                price_source=history_price_source,
                error=history_fetch_error,
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
                historical_market_data_agent = build_market_data_agent_output(
                    ticker=ticker,
                    period="max",
                    price_data=historical_window_data,
                    price_source=history_price_source,
                    data_window=data_window,
                )
                history_data_error = validate_price_data(
                    historical_window_data,
                    ticker=ticker,
                    min_rows=60,
                )

                if history_data_error:
                    historical_market_data_agent = build_market_data_agent_output(
                        ticker=ticker,
                        period="max",
                        price_data=historical_window_data,
                        price_source=history_price_source,
                        error=history_data_error,
                        data_window=data_window,
                    )
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

        evidence_agent = run_evidence_agent(
            technical=technical_agent["technical_analysis"],
            signals=technical_agent["signals"],
            news_analysis=news_agent["news_analysis"],
            fundamentals=fundamental_agent["fundamentals"],
            price_history_rows=len(price_data),
            include_news=include_news,
            include_fundamentals=include_fundamentals,
            backtest_evidence=backtest_evidence,
        )
        research_profile = evidence_agent["payload"]["research_profile"]
        ml_research, ml_prediction = build_ml_research_for_single_stock(
            ticker=ticker,
            include_ml=include_ml,
        )
        if ml_research.get("status") == "success":
            ml_research = apply_downside_risk_overlay(
                ml_research,
                build_current_downside_feature_snapshot(
                    price_data=price_data,
                    technical=technical_agent["technical_analysis"],
                    signals=technical_agent["signals"],
                    ml_research=ml_research,
                    base_snapshot=(ml_prediction or {}).get("feature_snapshot") or {},
                    risk_event_count=(
                        (news_agent.get("news_analysis") or {})
                        .get("summary", {})
                        .get("top_topics", {})
                        .get("risk_event", 0)
                    ),
                ),
            )
        ml_reference_trust = build_ml_reference_trust(ml_research, ml_prediction)
        exit_signal = build_exit_signal(
            technical=technical_agent["technical_analysis"],
            signals=technical_agent["signals"],
            ml_research=ml_research,
        )
        data_freshness = build_current_data_freshness(ticker=ticker)
        analyst_outputs = build_single_stock_analyst_outputs(
            technical=technical_agent["technical_analysis"],
            signals=technical_agent["signals"],
            fundamentals=fundamental_agent["fundamentals"],
            news_analysis=news_agent["news_analysis"],
            ml_research=ml_research,
            ml_reference_trust=ml_reference_trust,
            evidence_quality=research_profile["evidence_quality"],
            exit_signal=exit_signal,
            data_freshness=data_freshness,
        )
        analyst_consensus = build_analyst_consensus(analyst_outputs)
        agent_outputs = {
            "technical": wrap_legacy_agent_output(technical_agent),
            "news": wrap_legacy_agent_output(
                news_agent,
                fallback_used=news_agent.get("source") == "legacy_news_skill",
            ),
            "fundamental": wrap_legacy_agent_output(fundamental_agent),
            "backtest_evidence": build_agent_output(
                agent="backtest_evidence",
                status=map_backtest_evidence_status(backtest_evidence),
                summary=backtest_evidence.get("summary", ""),
                payload=backtest_evidence,
                warnings=build_backtest_evidence_warnings(backtest_evidence),
                metadata={
                    "ticker": ticker,
                    "source": "historical_signal_evidence",
                },
                fallback_used=False,
                legacy_fields=backtest_evidence,
            ),
            "ml_research": build_ml_research_agent_output(ticker, ml_research),
            "evidence": evidence_agent,
            "exit_signal": build_agent_output(
                agent="exit_signal",
                status=map_exit_signal_status(exit_signal),
                summary={
                    "exit_signal": exit_signal["exit_signal"],
                    "weakening_signal_20d": exit_signal["weakening_signal_20d"],
                    "email_alert_eligible": exit_signal["email_alert_eligible"],
                },
                payload=exit_signal,
                warnings=build_exit_signal_warnings(exit_signal),
                metadata={"ticker": ticker},
                fallback_used=False,
                legacy_fields=exit_signal,
            ),
        }
        orchestration = build_single_stock_orchestration_summary(
            {
                "market_data": market_data_agent,
                **agent_outputs,
            }
        )

        return {
            "intent": "single_stock_analysis",
            "status": "success",
            "query": user_query,
            "ticker": ticker,
            "price_source": price_source,
            "execution_plan": execution_plan,
            "orchestration": orchestration,
            "agent_outputs": agent_outputs,
            "analyst_outputs": analyst_outputs,
            "analyst_consensus": analyst_consensus,
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
            "ml_reference_trust": ml_reference_trust,
            "ml_trust_explanation": ml_reference_trust.get("explanation"),
            "exit_signal": exit_signal,
            "data_freshness": data_freshness,
        }

    def run_backtest_query(
        self,
        ticker: str,
        user_query: str,
        strategy_hint: str | None = None,
    ) -> dict:
        strategy = strategy_hint or select_backtest_strategy(user_query)
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
        market_data_agent = build_market_data_agent_output(
            ticker=ticker,
            period="max",
            price_data=price_data,
            price_source=price_source,
            error=fetch_error,
        )

        if fetch_error:
            return {
                "intent": "backtest_query",
                "strategy": strategy,
                "user_query": user_query,
                "execution_plan": execution_plan,
                **fetch_error,
            }

        backtest_price_data, data_window = build_price_data_window(price_data)
        market_data_agent = build_market_data_agent_output(
            ticker=ticker,
            period="max",
            price_data=backtest_price_data,
            price_source=price_source,
            data_window=data_window,
        )

        data_error = validate_price_data(
            backtest_price_data,
            ticker=ticker,
            min_rows=60,
        )

        if data_error:
            market_data_agent = build_market_data_agent_output(
                ticker=ticker,
                period="max",
                price_data=backtest_price_data,
                price_source=price_source,
                error=data_error,
                data_window=data_window,
            )
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
            strategy_hint=strategy,
        )
        _ = market_data_agent

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
            "data_freshness": build_backtest_data_freshness(data_window),
            "ml_reference": build_backtest_ml_reference(),
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
