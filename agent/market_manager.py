from agent.experts.backtest_agent import run_backtest_agent, select_backtest_strategy
from agent.experts.fundamental_agent import run_fundamental_agent
from agent.experts.news_agent import run_news_agent
from agent.experts.technical_agent import run_technical_agent
from agent.research_profile import build_research_profile
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

    def run_single_stock_analysis(
        self,
        ticker: str,
        user_query: str,
        include_news: bool = True,
        include_fundamentals: bool = True,
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
        )

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
            },
            "technical_analysis": technical_agent["technical_analysis"],
            "signals": technical_agent["signals"],
            "news": news_agent["news"],
            "news_analysis": news_agent["news_analysis"],
            "fundamentals": fundamental_agent["fundamentals"],
            "research_profile": research_profile,
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

        price_data, fetch_error, price_source = fetch_price_data(ticker, period="2y")

        if fetch_error:
            return {
                "intent": "backtest_query",
                "strategy": strategy,
                "user_query": user_query,
                "execution_plan": execution_plan,
                **fetch_error,
            }

        data_error = validate_price_data(price_data, ticker=ticker, min_rows=60)

        if data_error:
            return {
                "intent": "backtest_query",
                "strategy": strategy,
                "user_query": user_query,
                "execution_plan": execution_plan,
                "price_source": price_source,
                **data_error,
            }

        backtest_agent = run_backtest_agent(
            ticker=ticker,
            user_query=user_query,
            price_data=price_data,
        )

        return {
            "intent": "backtest_query",
            "ticker": ticker,
            "strategy": strategy,
            "user_query": user_query,
            "status": backtest_agent["status"],
            "price_source": price_source,
            "execution_plan": execution_plan,
            "agent_outputs": {
                "backtest": backtest_agent,
            },
            "report": backtest_agent["report"],
        }
