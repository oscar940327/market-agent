from strategies.breakout_strategy import check_breakout
from strategies.pullback_strategy import check_pullback_to_ma20
from strategies.volume_surge_strategy import check_volume_surge
from skills.technical_analysis_skill import analyze_moving_averages


def run_technical_agent(price_data) -> dict:
    technical_analysis = analyze_moving_averages(price_data)
    signals = {
        "breakout": check_breakout(price_data),
        "volume_surge": check_volume_surge(price_data),
        "pullback": check_pullback_to_ma20(price_data),
    }

    return {
        "agent": "technical",
        "status": "success",
        "technical_analysis": technical_analysis,
        "signals": signals,
        "summary": {
            "trend": technical_analysis["short_term_trend"],
            "is_above_ma20": technical_analysis["is_above_ma20"],
            "rsi14": technical_analysis["rsi14"],
            "macd_histogram": technical_analysis["macd_histogram"],
            "momentum_state": technical_analysis["momentum_state"],
            "breakout": signals["breakout"]["is_breakout"],
            "volume_surge": signals["volume_surge"]["is_volume_surge"],
            "pullback": signals["pullback"]["is_pullback"],
        },
    }
