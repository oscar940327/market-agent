from __future__ import annotations

import json
import os
import re

from agent.llm_analyst import OpenRouterChatClient
from agent.rule_based_router import SINGLE_STOCK_HOLDING_TERMS, query_contains_any


REPORT_REVIEW_VERSION = "report_review_v1"
MAX_REVIEW_ITERATIONS = 3
MAX_REVIEW_LLM_CALLS = 6

LLM_REVIEW_SYSTEM_PROMPT = """
You are the quality reviewer for a market research report. Check the report only
against the supplied structured context and deterministic findings. Do not give
new investment advice and do not invent facts. Return exactly one JSON object:
{"status":"pass|needs_revision","risk_notes":[],"suggested_fixes":[],
 "confidence_adjustment":"none|lower","reason":"short explanation"}
Use needs_revision only for factual inconsistency, omitted material risk,
overconfidence, or a workflow/section mismatch.
""".strip()

LLM_REVISER_SYSTEM_PROMPT = """
Revise the supplied market research report using only the structured context and
review findings. Preserve all supported numbers, section order, and disclaimers.
Do not add facts, recommendations, or new calculations. Return only the complete
revised report text. If a finding cannot be fixed from the context, disclose the
limitation instead of guessing.
""".strip()


def review_and_revise_report(
    *,
    kind: str,
    data: dict,
    report: str,
    mode: str | None = None,
    llm_client=None,
    max_iterations: int | None = None,
) -> dict:
    selected_mode = normalize_review_mode(
        mode or os.getenv("MARKET_AGENT_REPORT_REVIEW_MODE", "deterministic")
    )
    limit = normalize_max_iterations(max_iterations)
    current_report = report
    history = []
    deterministic = run_deterministic_review(kind=kind, data=data, report=current_report)
    history.append(_history_entry(0, "deterministic", deterministic))

    if deterministic["status"] == "pass" or selected_mode == "deterministic":
        return _result(
            report=current_report,
            deterministic=deterministic,
            history=history,
            mode_used="deterministic",
            iterations=0,
        )

    client = llm_client or get_review_llm_client_from_env()
    if client is None:
        return _result(
            report=current_report,
            deterministic=deterministic,
            history=history,
            mode_used="deterministic_fallback",
            iterations=0,
            fallback_reason="Review LLM is not configured.",
        )

    latest_review = deterministic
    latest_llm_review = None
    llm_calls = 0
    for iteration in range(1, limit + 1):
        if llm_calls >= MAX_REVIEW_LLM_CALLS:
            break
        try:
            llm_calls += 1
            llm_review = run_llm_review(
                client=client,
                kind=kind,
                data=data,
                report=current_report,
                deterministic=latest_review,
            )
        except Exception as error:
            history.append({"iteration": iteration, "stage": "llm_review", "status": "error", "message": str(error)})
            return _result(
                report=current_report,
                deterministic=latest_review,
                history=history,
                mode_used="hybrid_fallback",
                iterations=iteration - 1,
                client=client,
                fallback_reason=f"LLM reviewer failed: {error}",
            )

        history.append(_history_entry(iteration, "llm_review", llm_review))
        latest_llm_review = llm_review
        if llm_review["status"] == "pass" and latest_review["status"] == "pass":
            return _result(
                report=current_report,
                deterministic=latest_review,
                history=history,
                mode_used="hybrid",
                iterations=iteration - 1,
                client=client,
            )

        combined_findings = merge_review_findings(latest_review, llm_review)
        if llm_calls >= MAX_REVIEW_LLM_CALLS:
            break
        try:
            llm_calls += 1
            revised = run_llm_revision(
                client=client,
                kind=kind,
                data=data,
                report=current_report,
                findings=combined_findings,
            )
        except Exception as error:
            history.append({"iteration": iteration, "stage": "llm_revision", "status": "error", "message": str(error)})
            return _result(
                report=current_report,
                deterministic=latest_review,
                history=history,
                mode_used="hybrid_fallback",
                iterations=iteration - 1,
                client=client,
                fallback_reason=f"LLM reviser failed: {error}",
            )
        if not revised.strip():
            history.append({"iteration": iteration, "stage": "llm_revision", "status": "error", "message": "LLM reviser returned an empty report."})
            break
        current_report = revised.strip()
        latest_review = run_deterministic_review(kind=kind, data=data, report=current_report)
        history.append(_history_entry(iteration, "deterministic_after_revision", latest_review))
        if latest_review["status"] == "pass":
            if llm_calls >= MAX_REVIEW_LLM_CALLS:
                break
            try:
                llm_calls += 1
                final_llm_review = run_llm_review(
                    client=client,
                    kind=kind,
                    data=data,
                    report=current_report,
                    deterministic=latest_review,
                )
            except Exception as error:
                history.append({"iteration": iteration, "stage": "final_llm_review", "status": "error", "message": str(error)})
                return _result(
                    report=current_report,
                    deterministic=latest_review,
                    history=history,
                    mode_used="hybrid_fallback",
                    iterations=iteration,
                    client=client,
                    fallback_reason=f"Final LLM reviewer failed: {error}",
                )
            history.append(_history_entry(iteration, "final_llm_review", final_llm_review))
            latest_llm_review = final_llm_review
            if final_llm_review["status"] == "pass":
                return _result(
                    report=current_report,
                    deterministic=latest_review,
                    history=history,
                    mode_used="hybrid",
                    iterations=iteration,
                    client=client,
                )

    terminal_review = latest_review
    if latest_llm_review and latest_llm_review.get("status") == "needs_revision":
        terminal_review = {
            **latest_review,
            "status": "needs_revision",
            "risk_notes": merge_review_findings(latest_review, latest_llm_review)["risk_notes"],
            "suggested_fixes": merge_review_findings(latest_review, latest_llm_review)["suggested_fixes"],
            "confidence_adjustment": "lower",
        }
    return _result(
        report=current_report,
        deterministic=terminal_review,
        history=history,
        mode_used="hybrid",
        iterations=limit,
        client=client,
        fallback_reason=(
            "Maximum review LLM calls reached before all checks passed."
            if llm_calls >= MAX_REVIEW_LLM_CALLS
            else "Maximum review iterations reached before all checks passed."
        ),
    )


def run_deterministic_review(*, kind: str, data: dict, report: str) -> dict:
    checks = []
    _check(checks, "report_not_empty", bool(report.strip()), "Research Report 不可為空。", "重新建立固定格式報告。")
    if data.get("status") == "success":
        _check(checks, "risk_disclaimer", _has_disclaimer(report), "報告必須保留非投資建議或風險提醒。", "補回風險提醒與非投資建議聲明。")
        _review_required_sections(kind, data, report, checks)
        _review_single_stock_contract(kind, data, report, checks)
        _review_ml_trust(data, report, checks)
        _review_freshness(data, report, checks)
        _review_overconfidence(data, report, checks)
        _review_key_numbers(kind, data, report, checks)

    failed = [check for check in checks if check["status"] == "fail"]
    return {
        "review_version": REPORT_REVIEW_VERSION,
        "status": "needs_revision" if failed else "pass",
        "checks": checks,
        "risk_notes": [check["message"] for check in failed],
        "confidence_adjustment": "lower" if failed else "none",
        "suggested_fixes": [check["suggested_fix"] for check in failed],
    }


def run_llm_review(*, client, kind: str, data: dict, report: str, deterministic: dict) -> dict:
    raw = client.generate(
        LLM_REVIEW_SYSTEM_PROMPT,
        json.dumps(
            {
                "kind": kind,
                "structured_context": build_review_context(data),
                "deterministic_review": deterministic,
                "report": report,
            },
            ensure_ascii=False,
        ),
    )
    return validate_llm_review(parse_json_object(raw))


def run_llm_revision(*, client, kind: str, data: dict, report: str, findings: dict) -> str:
    return client.generate(
        LLM_REVISER_SYSTEM_PROMPT,
        json.dumps(
            {
                "kind": kind,
                "structured_context": build_review_context(data),
                "review_findings": findings,
                "report": report,
            },
            ensure_ascii=False,
        ),
    )


def build_review_context(data: dict) -> dict:
    return {
        "intent": data.get("intent"),
        "ticker": data.get("ticker"),
        "question_type": data.get("question_type"),
        "analyst_outputs": data.get("analyst_outputs", {}),
        "analyst_consensus": data.get("analyst_consensus", {}),
        "summary": data.get("summary", {}),
        "research_profile": data.get("research_profile", {}),
        "evidence_quality": data.get("evidence_quality", {}),
        "ml_reference_trust": data.get("ml_reference_trust", {}),
        "exit_signal": data.get("exit_signal", {}),
        "data_freshness": data.get("data_freshness", {}),
        "sector_summary": data.get("sector_summary", {}),
        "metrics": data.get("metrics", {}),
        "technical_analysis": data.get("technical_analysis", {}),
        "fundamentals": {
            "status": (data.get("fundamentals") or {}).get("status"),
            "metrics": (data.get("fundamentals") or {}).get("metrics", {}),
            "summary": (data.get("fundamentals") or {}).get("summary", {}),
        },
        "news_summary": (data.get("news_analysis") or {}).get("summary", {}),
        "ml_targets": (data.get("ml_research") or {}).get("targets", {}),
        "return_model": (data.get("ml_research") or {}).get("return_model", {}),
    }


def validate_llm_review(value: dict) -> dict:
    status = value.get("status")
    if status not in {"pass", "needs_revision"}:
        raise ValueError("LLM reviewer returned an invalid status.")
    adjustment = value.get("confidence_adjustment", "none")
    if adjustment not in {"none", "lower"}:
        raise ValueError("LLM reviewer returned an invalid confidence adjustment.")
    return {
        "review_version": REPORT_REVIEW_VERSION,
        "status": status,
        "checks": [],
        "risk_notes": _string_list(value.get("risk_notes")),
        "confidence_adjustment": adjustment,
        "suggested_fixes": _string_list(value.get("suggested_fixes")),
        "reason": str(value.get("reason") or "LLM semantic review completed."),
    }


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("LLM reviewer response must be a JSON object.")
    return value


def merge_review_findings(*reviews: dict) -> dict:
    return {
        "risk_notes": list(dict.fromkeys(note for review in reviews for note in review.get("risk_notes", []))),
        "suggested_fixes": list(dict.fromkeys(fix for review in reviews for fix in review.get("suggested_fixes", []))),
    }


def get_review_llm_client_from_env():
    if os.getenv("MARKET_AGENT_REPORT_REVIEW_PROVIDER", "openrouter").lower() != "openrouter":
        return None
    client = OpenRouterChatClient.from_env()
    if client is None:
        return None
    model = os.getenv("MARKET_AGENT_REPORT_REVIEW_MODEL", "").strip()
    if model:
        client.model = model
    return client


def normalize_review_mode(value: str | None) -> str:
    normalized = str(value or "deterministic").strip().lower()
    return normalized if normalized in {"deterministic", "hybrid"} else "deterministic"


def normalize_max_iterations(value: int | None) -> int:
    if value is None:
        try:
            value = int(os.getenv("MARKET_AGENT_REPORT_REVIEW_MAX_ITERATIONS", str(MAX_REVIEW_ITERATIONS)))
        except ValueError:
            value = MAX_REVIEW_ITERATIONS
    return max(1, min(MAX_REVIEW_ITERATIONS, int(value)))


def _review_required_sections(kind: str, data: dict, report: str, checks: list[dict]) -> None:
    required = {
        "single_stock": ["研究摘要", "基本面分析", "技術面分析", "新聞面分析", "ML Reference", "綜合評估", "風險提醒"],
        "backtest": ["績效摘要", "風險提醒"],
        "theme": ["風險提醒"],
        "portfolio": ["風險提醒"],
    }.get(kind, [])
    for title in required:
        _check(checks, f"required_section:{title}", title in report, f"報告缺少必要段落：{title}。", f"補上「{title}」段落。")
    theme_ml = data.get("theme_ml_reference") or data.get("ml_research") or {}
    if kind == "theme" and theme_ml.get("status") == "success":
        _check(checks, "required_section:ML Reference", "ML Reference" in report, "主題報告缺少 ML Reference。", "補上 ML Reference 段落。")


def _review_single_stock_contract(kind: str, data: dict, report: str, checks: list[dict]) -> None:
    if kind != "single_stock":
        return
    holding = _is_holding_question(data)
    has_exit_section = "持有風險 / 出場觀察" in report
    _check(
        checks,
        "holding_section_matches_question",
        has_exit_section if holding else not has_exit_section,
        "持有／出場段落與問題類型不一致。",
        "依 question_type 新增或移除持有風險段落。",
    )


def _review_ml_trust(data: dict, report: str, checks: list[dict]) -> None:
    trust = data.get("ml_reference_trust") or data.get("theme_ml_reference_trust") or {}
    if trust.get("status") != "reduced_trust":
        return
    disclosed = any(phrase in report for phrase in ("降低信任", "保守解讀", "信任度降低"))
    _check(checks, "ml_reduced_trust_disclosed", disclosed, "ML Reference 為 reduced_trust，但報告未清楚揭露。", "加入 ML Reference 降低信任與保守解讀說明。")


def _review_freshness(data: dict, report: str, checks: list[dict]) -> None:
    freshness = data.get("data_freshness") or {}
    if freshness.get("overall") not in {"warning", "stale", "missing"}:
        return
    disclosed = any(phrase in report for phrase in ("資料新鮮度", "資料延遲", "資料不完整", "Structured Data"))
    _check(checks, "freshness_warning_disclosed", disclosed, "資料有 freshness warning，但報告未揭露。", "在風險提醒揭露資料新鮮度問題。")


def _review_overconfidence(data: dict, report: str, checks: list[dict]) -> None:
    prohibited = ("一定會上漲", "保證獲利", "現在一定要買", "應立即買進", "必須買進")
    has_overconfidence = any(phrase in report for phrase in prohibited)
    _check(checks, "no_overconfident_claim", not has_overconfidence, "報告包含無法由證據支持的確定性投資語句。", "改成研究觀察語氣並揭露不確定性。")
    evidence = data.get("evidence_quality") or {}
    if evidence.get("level") == "high":
        conflated = "證據品質高，因此適合買進" in report
        _check(checks, "evidence_not_trade_confidence", not conflated, "報告把 Evidence Quality 誤解成買進信心。", "說明 Evidence Quality 代表資料可信程度，不代表方向。")


def _review_key_numbers(kind: str, data: dict, report: str, checks: list[dict]) -> None:
    if kind in {"single_stock", "theme"}:
        ml = data.get("ml_research") or data.get("theme_ml_reference") or {}
        if ml.get("status") == "success" and "ML Reference" in report:
            for target_name in ("up_5d", "up_10d", "up_20d", "large_drop_20d"):
                target = (ml.get("targets") or {}).get(target_name) or {}
                percent = target.get("probability_percent")
                if percent is None and target.get("probability") is not None:
                    percent = float(target["probability"]) * 100
                if percent is None:
                    continue
                formatted = f"{float(percent):.1f}%"
                _check(
                    checks,
                    f"ml_number_present:{target_name}",
                    formatted in report,
                    f"報告未保留 {target_name} 的結構化機率 {formatted}。",
                    f"使用 Structured Data 的 {formatted}，不要自行改算。",
                )
    if kind == "backtest":
        metrics = data.get("metrics") or {}
        total = metrics.get("total_trades")
        if total is not None:
            _check(checks, "backtest_trade_count", str(total) in report, "回測報告未保留總交易次數。", "補回 Structured Data 的 total_trades。")


def _has_disclaimer(report: str) -> bool:
    return "不構成投資建議" in report or "風險提醒" in report


def _is_holding_question(data: dict) -> bool:
    if data.get("question_type"):
        return data["question_type"] == "holding_exit"
    query = str(data.get("query") or "")
    return query_contains_any(query, query.lower(), SINGLE_STOCK_HOLDING_TERMS)


def _check(checks: list[dict], code: str, passed: bool, message: str, suggested_fix: str) -> None:
    checks.append({"code": code, "status": "pass" if passed else "fail", "message": message, "suggested_fix": suggested_fix})


def _history_entry(iteration: int, stage: str, review: dict) -> dict:
    return {
        "iteration": iteration,
        "stage": stage,
        "status": review.get("status"),
        "risk_notes": review.get("risk_notes", []),
        "suggested_fixes": review.get("suggested_fixes", []),
    }


def _result(*, report, deterministic, history, mode_used, iterations, client=None, fallback_reason=None):
    review = {
        **deterministic,
        "mode_used": mode_used,
        "iterations": iterations,
        "max_iterations": MAX_REVIEW_ITERATIONS,
        "provider": getattr(client, "provider", None),
        "model": getattr(client, "model", None),
        "fallback_used": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "history": history,
    }
    return {"report": report, "review": review}


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
