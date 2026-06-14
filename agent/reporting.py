import os

from agent.analyst import (
    format_backtest_analysis,
    format_error_message,
    format_portfolio_analysis,
    format_single_stock_analysis,
    format_theme_analysis,
)
from agent.llm_analyst import OpenAIResponsesClient, generate_llm_report
from agent.llm_analyst import OpenRouterChatClient


SUPPORTED_ANALYST_MODES = {"rule_based", "llm"}


def get_default_analyst_mode() -> str:
    return normalize_analyst_mode(os.getenv("MARKET_AGENT_ANALYST_MODE", "rule_based"))


def normalize_analyst_mode(analyst_mode: str | None) -> str:
    if not analyst_mode:
        return "rule_based"

    normalized = analyst_mode.strip().lower()

    if normalized in SUPPORTED_ANALYST_MODES:
        return normalized

    return "rule_based"


def build_report(
    *,
    kind: str,
    data: dict,
    analyst_mode: str | None = None,
    llm_client=None,
) -> dict:
    fallback_report = build_rule_based_report(kind=kind, data=data)
    requested_mode = normalize_analyst_mode(analyst_mode or get_default_analyst_mode())

    if data.get("status") != "success":
        return {
            "report": fallback_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                fallback_used=True,
                message="非 success 狀態一律使用 rule-based error report。",
            ),
        }

    if requested_mode == "rule_based":
        return {
            "report": fallback_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                fallback_used=False,
                message="使用 rule-based analyst。",
            ),
        }

    client = llm_client or get_llm_client_from_env()

    if client is None:
        return {
            "report": fallback_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                fallback_used=True,
                message="未設定 LLM provider，已 fallback 到 rule-based analyst。",
            ),
        }

    try:
        llm_report = generate_llm_report(kind=kind, data=data, llm_client=client)
    except Exception as error:
        return {
            "report": fallback_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                provider=getattr(client, "provider", None),
                model=getattr(client, "model", None),
                fallback_used=True,
                message=f"LLM analyst 產生失敗，已 fallback：{error}",
            ),
        }

    return {
        "report": llm_report,
        "analyst": build_analyst_metadata(
            requested_mode=requested_mode,
            mode_used="llm",
            provider=getattr(client, "provider", None),
            model=getattr(client, "model", None),
            fallback_used=False,
            message="使用 LLM analyst 解釋 structured analysis data。",
        ),
    }


def build_rule_based_report(kind: str, data: dict) -> str:
    if data.get("status") != "success":
        return format_error_message(data)

    if kind == "single_stock":
        return format_single_stock_analysis(data)

    if kind == "backtest":
        return format_backtest_analysis(data)

    if kind == "theme":
        return format_theme_analysis(data)

    if kind == "portfolio":
        return format_portfolio_analysis(data)

    return format_error_message(
        {
            "status": "unsupported_report_kind",
            "message": f"不支援的 report kind：{kind}",
        }
    )


def get_llm_client_from_env():
    provider = os.getenv("MARKET_AGENT_LLM_PROVIDER", "openai").strip().lower()

    if provider == "openrouter":
        return OpenRouterChatClient.from_env()

    return OpenAIResponsesClient.from_env()


def build_analyst_metadata(
    *,
    requested_mode: str,
    mode_used: str,
    fallback_used: bool,
    message: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    return {
        "requested_mode": requested_mode,
        "mode_used": mode_used,
        "provider": provider,
        "model": model,
        "fallback_used": fallback_used,
        "message": message,
    }
