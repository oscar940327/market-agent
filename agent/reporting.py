import os

from agent.analyst import (
    format_backtest_analysis,
    format_error_message,
    format_portfolio_analysis,
    format_single_stock_analysis,
    format_theme_analysis,
)
from agent.fixed_single_stock_report import build_fixed_single_stock_report
from agent.llm_analyst import OpenAIResponsesClient, generate_llm_report
from agent.llm_analyst import OpenRouterChatClient
from agent.report_context import build_single_stock_report_context


try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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

    if kind == "single_stock":
        fixed_report = build_fixed_single_stock_report(data)
        return {
            "report": fixed_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                fallback_used=False,
                message="使用固定格式 single-stock report，避免 LLM 改變 Research Report 版型。",
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

    llm_report = apply_required_report_sections(
        kind=kind,
        data=data,
        report=llm_report,
    )

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


def apply_required_report_sections(*, kind: str, data: dict, report: str) -> str:
    if kind != "single_stock" or data.get("status") != "success":
        return report

    context = build_single_stock_report_context(data)
    if context.get("question_type") != "holding_exit":
        return remove_report_section(
            report,
            section_titles=["持有風險 / 出場觀察"],
            following_titles=["綜合評估", "資料與風險提醒", "風險提醒"],
        )

    if not context.get("exit_signal"):
        return report

    if "持有風險 / 出場觀察" in report:
        return report

    section = format_required_exit_signal_section(context.get("exit_signal"))
    return insert_section_before_summary(report, section)


def format_required_exit_signal_section(exit_signal: dict | None) -> str:
    lines = ["持有風險 / 出場觀察"]

    if not exit_signal:
        lines.append("目前沒有 exit signal 資料，因此無法完整判斷是否需要減碼。")
        return "\n".join(lines)

    if exit_signal.get("status") != "success":
        reason = exit_signal.get("reason") or "出場觀察資料不足。"
        lines.append(f"狀態：{exit_signal.get('status', 'unknown')}。{reason}")
        return "\n".join(lines)

    signal = exit_signal.get("exit_signal", "unknown")
    weakening = exit_signal.get("weakening_signal_20d", "unknown")
    reason = exit_signal.get("reason") or ""
    action_note = exit_signal.get("action_note") or ""
    reasons = exit_signal.get("reasons") or []

    lines.extend(
        [
            f"目前 exit signal 為「{signal}」。",
            f"20 日轉弱風險為「{weakening}」。",
        ]
    )
    if reason:
        lines.append(f"判斷原因：{reason}")
    if reasons:
        lines.append("主要觀察點：")
        lines.extend(f"- {item}" for item in reasons)
    if action_note:
        lines.append(f"如果已持有：{action_note}")

    lines.append("這是持有風險觀察，不是直接買賣指令。")
    return "\n".join(lines)


def insert_section_before_summary(report: str, section: str) -> str:
    marker = "\n綜合評估"
    if marker in report:
        return report.replace(marker, f"\n{section}\n{marker}", 1)

    marker = "\n風險提醒"
    if marker in report:
        return report.replace(marker, f"\n{section}\n{marker}", 1)

    return f"{report.rstrip()}\n\n{section}"


def remove_report_section(
    report: str,
    *,
    section_titles: list[str],
    following_titles: list[str],
) -> str:
    lines = report.splitlines()
    result = []
    skip = False

    for line in lines:
        stripped = line.strip()
        if stripped in section_titles:
            skip = True
            continue
        if skip and stripped in following_titles:
            skip = False
        if not skip:
            result.append(line)

    return "\n".join(result).strip()


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
