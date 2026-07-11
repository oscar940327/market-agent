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
from agent.ml_trust_explanation import format_ml_trust_explanation_lines
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

    if kind == "backtest":
        return {
            "report": fallback_report,
            "analyst": build_analyst_metadata(
                requested_mode=requested_mode,
                mode_used="rule_based",
                fallback_used=False,
                message="使用固定格式 backtest report，避免 LLM 改變策略回測數字與版型。",
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
    if kind == "theme" and data.get("status") == "success":
        report = ensure_theme_ml_reference_section(data=data, report=report)
        return enforce_theme_ml_reference_trust(data=data, report=report)

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


def ensure_theme_ml_reference_section(*, data: dict, report: str) -> str:
    ml_reference = data.get("theme_ml_reference") or data.get("ml_research") or {}
    if ml_reference.get("status") != "success":
        return report
    if "ML Reference" in report:
        return report

    section = format_theme_ml_reference_section(ml_reference)
    return insert_theme_section_before_risk(report, section)


def enforce_theme_ml_reference_trust(*, data: dict, report: str) -> str:
    trust = data.get("theme_ml_reference_trust") or data.get("ml_reference_trust") or {}
    updated_report = report

    if trust.get("status") == "reduced_trust":
        reduced_trust_text = "ML Reference 目前為降低信任狀態，相關數字需保守解讀"
        replacements = [
            "ML 參考信任度為一般",
            "ML Reference 信任度為一般",
            "ML 參考信任度為正常",
            "ML Reference 信任度為正常",
            "ML 參考信任度一般",
            "ML Reference 信任度一般",
        ]
        for phrase in replacements:
            updated_report = updated_report.replace(phrase, reduced_trust_text)

    explanation_lines = format_ml_trust_explanation_lines(trust.get("explanation"))
    if (
        "ML Reference" in updated_report
        and explanation_lines
        and "ML 信任說明:" not in updated_report
    ):
        explanation_block = "ML 信任說明:\n" + "\n".join(explanation_lines)
        updated_report = updated_report.replace(
            "ML Reference",
            f"ML Reference\n{explanation_block}",
            1,
        )

    return updated_report


def format_theme_ml_reference_section(ml_reference: dict) -> str:
    coverage = ml_reference.get("coverage") or {}
    source = ml_reference.get("source") or {}
    targets = ml_reference.get("targets") or {}
    signal_counts = ml_reference.get("constituent_signal_counts") or {}

    lines = [
        "ML Reference",
        (
            "本主題 ML Reference 來自主題內個股的已儲存每日預測彙總，"
            "用來輔助判斷主題短線機率與風險。"
        ),
        "",
        f"- ML 覆蓋：{coverage.get('covered_ticker_count', 0)}/{coverage.get('total_ticker_count', 0)} 檔。",
        f"- ML 資料狀態：aggregated / {source.get('prediction_freshness', 'unknown')}。",
        format_theme_ml_probability_line("5 個交易日平均上漲機率", targets.get("up_5d")),
        format_theme_ml_probability_line("10 個交易日平均上漲機率", targets.get("up_10d")),
        format_theme_ml_probability_line("20 個交易日平均上漲機率", targets.get("up_20d")),
        format_theme_ml_probability_line("20 個交易日內平均大跌風險", targets.get("large_drop_20d")),
        f"- 主題 ML 判斷：{ml_reference.get('theme_signal', 'unknown')}。",
    ]
    if signal_counts:
        lines.append(f"- 20 日方向統計：{format_key_value_counts(signal_counts)}。")

    return "\n".join(line for line in lines if line is not None)


def format_theme_ml_probability_line(label: str, target: dict | None) -> str:
    target = target or {}
    probability = target.get("probability_percent")
    signal_label = target.get("signal_label") or "unknown"
    if probability is None:
        return f"- {label}：資料不足。"
    return f"- {label}：{probability:.1f}%，{signal_label}。"


def format_key_value_counts(counts: dict) -> str:
    return "，".join(f"{key} {value} 檔" for key, value in counts.items())


def insert_theme_section_before_risk(report: str, section: str) -> str:
    markers = [
        "\n風險提醒",
        "\n風險",
        "\n不構成投資建議",
    ]
    for marker in markers:
        if marker in report:
            return report.replace(marker, f"\n{section}\n{marker}", 1)

    return f"{report.rstrip()}\n\n{section}"


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
    reason = remove_duplicate_exit_weakening_reason(
        exit_signal.get("reason") or "",
        weakening,
    )
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


def remove_duplicate_exit_weakening_reason(reason: str, weakening: str) -> str:
    text = reason.strip()
    if not text:
        return ""

    duplicates = [
        f"20 日轉弱風險為 {weakening}。",
        f"20 日轉弱風險為「{weakening}」。",
        f"20 日轉弱風險為 {weakening}",
        f"20 日轉弱風險為「{weakening}」",
    ]
    for duplicate in duplicates:
        text = text.replace(duplicate, "")
    return " ".join(text.split()).strip()


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
        report = ensure_theme_ml_reference_section(
            data=data,
            report=format_theme_analysis(data),
        )
        return enforce_theme_ml_reference_trust(data=data, report=report)

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
