from data.themes import THEMES


def run_portfolio_agent(holdings: list[dict], analyses: list[dict]) -> dict:
    normalized_holdings = normalize_holdings(holdings)
    holding_by_ticker = {
        holding["ticker"]: holding
        for holding in normalized_holdings
    }
    positions = []

    for analysis in analyses:
        ticker = analysis.get("ticker", "")
        holding = holding_by_ticker.get(ticker, {"ticker": ticker, "weight": 0})
        positions.append(
            build_position_summary(
                holding=holding,
                analysis=analysis,
            )
        )

    concentration = calculate_concentration(normalized_holdings)
    theme_exposure = calculate_theme_exposure(normalized_holdings)
    risk_summary = build_portfolio_risk_summary(
        concentration=concentration,
        theme_exposure=theme_exposure,
        positions=positions,
    )

    return {
        "agent": "portfolio",
        "status": "success",
        "holdings": normalized_holdings,
        "positions": positions,
        "concentration": concentration,
        "theme_exposure": theme_exposure,
        "risk_summary": risk_summary,
        "summary": {
            "holding_count": len(normalized_holdings),
            "largest_position": concentration["largest_position"],
            "largest_weight": concentration["largest_weight"],
            "largest_theme": theme_exposure["largest_theme"],
            "largest_theme_weight": theme_exposure["largest_theme_weight"],
            "risk_level": risk_summary["risk_level"],
        },
    }


def normalize_holdings(holdings: list[dict]) -> list[dict]:
    cleaned = []

    for holding in holdings:
        ticker = str(holding.get("ticker", "")).strip().upper()

        if not ticker:
            continue

        market_value = normalize_number(holding.get("market_value"))
        quantity = normalize_number(holding.get("quantity"))
        cost_basis = normalize_number(holding.get("cost_basis"))

        cleaned.append(
            {
                "ticker": ticker,
                "market_value": market_value,
                "quantity": quantity,
                "cost_basis": cost_basis,
            }
        )

    total_market_value = sum(
        holding["market_value"]
        for holding in cleaned
        if isinstance(holding["market_value"], (int, float))
    )
    equal_weight = round(1 / len(cleaned), 4) if cleaned else 0

    for holding in cleaned:
        if total_market_value > 0 and isinstance(holding["market_value"], (int, float)):
            holding["weight"] = round(holding["market_value"] / total_market_value, 4)
        else:
            holding["weight"] = equal_weight

        holding["themes"] = find_ticker_themes(holding["ticker"])

    return cleaned


def normalize_number(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_ticker_themes(ticker: str) -> list[str]:
    matched_themes = []

    for theme_key, theme in THEMES.items():
        if ticker in theme["tickers"]:
            matched_themes.append(theme_key)

    if not matched_themes:
        matched_themes.append("unclassified")

    return matched_themes


def calculate_concentration(holdings: list[dict]) -> dict:
    if not holdings:
        return {
            "holding_count": 0,
            "largest_position": None,
            "largest_weight": 0,
            "top_3_weight": 0,
            "position_concentration": "no_data",
        }

    sorted_holdings = sorted(
        holdings,
        key=lambda holding: holding["weight"],
        reverse=True,
    )
    largest_holding = sorted_holdings[0]
    top_3_weight = round(sum(holding["weight"] for holding in sorted_holdings[:3]), 4)

    return {
        "holding_count": len(holdings),
        "largest_position": largest_holding["ticker"],
        "largest_weight": largest_holding["weight"],
        "top_3_weight": top_3_weight,
        "position_concentration": classify_position_concentration(
            largest_weight=largest_holding["weight"],
            top_3_weight=top_3_weight,
        ),
    }


def classify_position_concentration(largest_weight: float, top_3_weight: float) -> str:
    if largest_weight >= 0.35 or top_3_weight >= 0.75:
        return "high"

    if largest_weight >= 0.25 or top_3_weight >= 0.6:
        return "medium"

    return "low"


def calculate_theme_exposure(holdings: list[dict]) -> dict:
    exposure = {}

    for holding in holdings:
        themes = holding.get("themes", ["unclassified"])
        weight_per_theme = holding["weight"] / len(themes)

        for theme in themes:
            exposure[theme] = exposure.get(theme, 0) + weight_per_theme

    rounded_exposure = {
        theme: round(weight, 4)
        for theme, weight in sorted(
            exposure.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    }

    if not rounded_exposure:
        return {
            "exposure": {},
            "largest_theme": None,
            "largest_theme_weight": 0,
            "theme_concentration": "no_data",
        }

    largest_theme, largest_weight = next(iter(rounded_exposure.items()))

    return {
        "exposure": rounded_exposure,
        "largest_theme": largest_theme,
        "largest_theme_weight": largest_weight,
        "theme_concentration": classify_theme_concentration(largest_weight),
    }


def classify_theme_concentration(largest_theme_weight: float) -> str:
    if largest_theme_weight >= 0.5:
        return "high"

    if largest_theme_weight >= 0.35:
        return "medium"

    return "low"


def build_position_summary(holding: dict, analysis: dict) -> dict:
    if analysis.get("status") != "success":
        return {
            "ticker": holding.get("ticker", analysis.get("ticker", "")),
            "weight": holding.get("weight", 0),
            "status": analysis.get("status"),
            "risk_flags": [analysis.get("message", "分析未完成")],
            "setup_quality": "unknown",
            "risk_level": "unknown",
        }

    technical = analysis["technical_analysis"]
    research_profile = analysis["research_profile"]
    risk_flags = []

    if technical["short_term_trend"] == "weak":
        risk_flags.append("短線趨勢偏弱")

    if not technical["is_above_ma20"]:
        risk_flags.append("價格低於 MA20")

    if research_profile["risk_level"] == "high":
        risk_flags.append("單股研究風險偏高")

    if not risk_flags:
        risk_flags.append("目前沒有明顯單股風險旗標")

    return {
        "ticker": holding["ticker"],
        "weight": holding["weight"],
        "status": "success",
        "themes": holding.get("themes", []),
        "short_term_trend": technical["short_term_trend"],
        "setup_quality": research_profile["setup_quality"],
        "risk_level": research_profile["risk_level"],
        "risk_flags": risk_flags,
    }


def build_portfolio_risk_summary(
    concentration: dict,
    theme_exposure: dict,
    positions: list[dict],
) -> dict:
    risk_factors = []

    if concentration["position_concentration"] == "high":
        risk_factors.append("單一或前三大持股集中度偏高")
    elif concentration["position_concentration"] == "medium":
        risk_factors.append("持股集中度中等")

    if theme_exposure["theme_concentration"] == "high":
        risk_factors.append("主題 / 產業集中度偏高")
    elif theme_exposure["theme_concentration"] == "medium":
        risk_factors.append("主題 / 產業集中度中等")

    weak_positions = [
        position["ticker"]
        for position in positions
        if position.get("short_term_trend") == "weak"
    ]

    if weak_positions:
        risk_factors.append(f"短線轉弱標的：{', '.join(weak_positions)}")

    if not risk_factors:
        risk_factors.append("目前沒有明顯 portfolio-level 風險旗標")

    return {
        "risk_level": classify_portfolio_risk(
            concentration=concentration,
            theme_exposure=theme_exposure,
            weak_position_count=len(weak_positions),
        ),
        "risk_factors": risk_factors,
        "weak_positions": weak_positions,
    }


def classify_portfolio_risk(
    concentration: dict,
    theme_exposure: dict,
    weak_position_count: int,
) -> str:
    if (
        concentration["position_concentration"] == "high"
        or theme_exposure["theme_concentration"] == "high"
        or weak_position_count >= 3
    ):
        return "high"

    if (
        concentration["position_concentration"] == "medium"
        or theme_exposure["theme_concentration"] == "medium"
        or weak_position_count >= 1
    ):
        return "medium"

    return "low"
