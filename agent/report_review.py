from __future__ import annotations

import json
import os
import re

from agent.llm_analyst import (
    OpenRouterChatClient,
    summarize_theme_fundamentals,
    summarize_theme_news,
)
from agent.json_parsing import parse_first_json_object
from agent.rule_based_router import SINGLE_STOCK_HOLDING_TERMS, query_contains_any


REPORT_REVIEW_VERSION = "report_review_v3"
MAX_REVIEW_ITERATIONS = 3
MAX_REVIEW_LLM_CALLS = 7
MIN_PASSING_QUALITY_SCORE = 4
QUALITY_SCORE_FIELDS = (
    "query_relevance",
    "evidence_consistency",
    "risk_balance",
    "clarity",
    "hallucination_safety",
    "overall_quality",
)
INTERNAL_REVIEW_TERMS = (
    "deterministic_review",
    "deterministic review",
    "semantic_review",
    "semantic review",
    "confidence_adjustment",
    "review_findings",
    "review findings",
)

LLM_REVIEW_SYSTEM_PROMPT = """
You are the quality reviewer for a market research report. Check the report only
against the supplied structured context and deterministic findings. Do not give
new investment advice and do not invent facts. Score every quality dimension
from 1 (poor) to 5 (excellent). Return exactly one JSON object:
{"status":"pass|needs_revision","quality_scores":{"query_relevance":1,
 "evidence_consistency":1,"risk_balance":1,"clarity":1,
 "hallucination_safety":1,"overall_quality":1},"risk_notes":[],
 "suggested_fixes":[],"confidence_adjustment":"none|lower",
 "reason":"short explanation"}
Use pass only when every score is at least 4 and there is no factual
inconsistency, omitted material risk, unanswered user intent, overconfidence,
hallucination, or workflow/section mismatch.

Treat raw structured fields as authoritative. In particular,
news_summary.sentiment is the factual aggregate sentiment. Specialist stances
are interpretations and must not override that field. A concrete news event or
headline is supported only when it appears in news_events_summary; topic counts
alone do not support inventing a named event.

For holding_exit questions, every representative news event with importance
high, sentiment negative, and topic risk_event is a material risk and must be
disclosed. For theme reports, use theme_news_summary as the aggregate source and
do not treat backtest_sample=not_applicable as missing historical evidence.
Each ML target's signal_quality has its own scope; verify that a medium-quality
large_drop_20d signal is not described as low quality merely because the upside
targets are low quality.

Interpret quality fields at their documented scope:
- evidence_quality.level is the overall research evidence level.
- return_reference.evidence_quality describes only the historical-similarity
  sample, not the whole report and not model quality.
- ml_reference_trust describes whether ML outputs should be trusted normally or
  conservatively. A high historical-sample quality can coexist with medium
  overall evidence and reduced ML trust; this is not a contradiction when the
  report labels each scope clearly.
- A freshness warning applies only to the named source. Do not claim every data
  source is stale when only ML training data is stale.

For an entry/research question, do not require a holding/exit section. Material
risk from exit_signal or weakening_signal_20d must still be reflected as an
entry-risk warning without turning it into a direct sell instruction.

Fundamental growth values are ratios in structured context. For example, 3.457
must be displayed as 345.7%, not 3.457%. Do not penalize a correctly converted
percentage, but require the report to identify it as a provider-reported growth
metric whose period follows the source data.
""".strip()

LLM_REVISER_SYSTEM_PROMPT = """
Revise the supplied market research report using only the structured context and
review findings. Preserve all supported numbers, section order, and disclaimers.
Do not add facts, recommendations, or new calculations. Return only the complete
revised report text. If a finding cannot be fixed from the context, disclose the
limitation instead of guessing.

The structured context contains immutable_facts. Every listed display value is
authoritative and must remain exactly unchanged. Never rescale, round again, or
replace those values. Keep overall evidence quality, historical-similarity
evidence quality, and ML trust as separate concepts. For non-holding questions,
describe material exit/weakening findings only as entry-risk context and do not
add a holding/exit section.

Never mention the reviewer, review findings, deterministic review, semantic
review, checks, confidence_adjustment, revision iterations, or internal workflow
metadata in the revised report. Fix the report content directly.

Use news_summary.sentiment as the authoritative aggregate news sentiment. Do
not replace it with an interpretive specialist stance. Mention a concrete news
event or headline only when it exists in news_events_summary; otherwise describe
only the supplied topic and count.

For holding_exit questions, explicitly disclose every representative high-
importance negative risk_event from news_events_summary. For theme reports,
identify theme_news_summary as the aggregate source, preserve each ML target's
own signal_quality, and describe backtest_sample=not_applicable as not applicable
rather than missing evidence.
""".strip()


def review_and_revise_report(
    *,
    kind: str,
    data: dict,
    report: str,
    mode: str | None = None,
    llm_client=None,
    revision_llm_client=None,
    max_iterations: int | None = None,
) -> dict:
    selected_mode = normalize_review_mode(
        mode or os.getenv("MARKET_AGENT_REPORT_REVIEW_MODE", "deterministic")
    )
    limit = normalize_max_iterations(max_iterations)
    current_report = strip_internal_review_metadata(report)
    history = []
    deterministic = run_deterministic_review(kind=kind, data=data, report=current_report)
    history.append(_history_entry(0, "deterministic", deterministic))

    semantic_required = selected_mode == "semantic"
    if selected_mode == "deterministic" or (
        deterministic["status"] == "pass" and not semantic_required
    ):
        return _result(
            report=current_report,
            deterministic=deterministic,
            history=history,
            mode_used="deterministic",
            iterations=0,
            max_iterations=limit,
        )

    supplied_review_client = llm_client is not None
    client = llm_client or get_review_llm_client_from_env()
    if client is None:
        terminal = deterministic
        if semantic_required and deterministic["status"] == "pass":
            terminal = {
                **deterministic,
                "status": "needs_revision",
                "risk_notes": ["Semantic quality review could not run."],
                "suggested_fixes": ["Configure the report review LLM and rerun the fixture."],
                "confidence_adjustment": "lower",
            }
        return _result(
            report=current_report,
            deterministic=terminal,
            history=history,
            mode_used="deterministic_fallback",
            iterations=0,
            max_iterations=limit,
            fallback_reason="Review LLM is not configured.",
        )

    reviser = revision_llm_client or (
        client if supplied_review_client else get_revision_llm_client_from_env()
    ) or client
    latest_review = deterministic
    latest_llm_review = None
    llm_calls = 0
    revisions = 0
    while llm_calls < MAX_REVIEW_LLM_CALLS:
        iteration = revisions + 1
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
                mode_used=f"{selected_mode}_fallback",
                iterations=revisions,
                max_iterations=limit,
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
                mode_used=selected_mode,
                iterations=revisions,
                max_iterations=limit,
                client=client,
                semantic_review=llm_review,
            )

        if revisions >= limit:
            break
        combined_findings = merge_review_findings(latest_review, llm_review)
        if llm_calls >= MAX_REVIEW_LLM_CALLS:
            break
        try:
            llm_calls += 1
            revised = run_llm_revision(
                client=reviser,
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
                mode_used=f"{selected_mode}_fallback",
                iterations=revisions,
                max_iterations=limit,
                client=client,
                semantic_review=llm_review,
                fallback_reason=f"LLM reviser failed: {error}",
            )
        if not revised.strip():
            history.append({"iteration": iteration, "stage": "llm_revision", "status": "error", "message": "LLM reviser returned an empty report."})
            break
        current_report = strip_internal_review_metadata(
            restore_immutable_report_numbers(
                kind=kind,
                data=data,
                report=revised.strip(),
            )
        )
        revisions += 1
        latest_review = run_deterministic_review(kind=kind, data=data, report=current_report)
        history.append(_history_entry(iteration, "deterministic_after_revision", latest_review))

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
        mode_used=selected_mode,
        iterations=revisions,
        max_iterations=limit,
        client=client,
        semantic_review=latest_llm_review,
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
        _review_internal_metadata(report, checks)
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
    successful_theme_results = [
        result
        for result in (data.get("results") or [])
        if result.get("status") == "success"
    ]
    theme_news_summary = (
        summarize_theme_news(successful_theme_results)
        if data.get("theme_key") or data.get("theme_name")
        else {}
    )
    theme_fundamental_summary = (
        summarize_theme_fundamentals(successful_theme_results)
        if data.get("theme_key") or data.get("theme_name")
        else {}
    )
    single_stock_news_summary = (data.get("news_analysis") or {}).get("summary", {})
    return {
        "intent": data.get("intent"),
        "query": data.get("query") or (data.get("route") or {}).get("query"),
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
        "news_summary": single_stock_news_summary or theme_news_summary,
        "theme_news_summary": theme_news_summary,
        "theme_fundamental_summary": theme_fundamental_summary,
        "news_events_summary": (
            (data.get("agent_outputs", {}).get("news", {}) or {}).get("news_events_summary")
            or (
                (data.get("agent_outputs", {}).get("news", {}) or {}).get("payload", {})
                or {}
            ).get("news_events_summary")
        ),
        "ml_targets": (data.get("ml_research") or {}).get("targets", {}),
        "return_model": (data.get("ml_research") or {}).get("return_model", {}),
        "quality_scope_definitions": {
            "overall_evidence": "evidence_quality.level evaluates the complete research payload.",
            "historical_similarity_evidence": "ml_research.return_reference.evidence_quality evaluates only the historical-similarity sample.",
            "ml_reference_trust": "ml_reference_trust controls how conservatively ML outputs should be interpreted.",
        },
        "immutable_facts": build_immutable_facts(data),
    }


def build_immutable_facts(data: dict) -> dict:
    facts = {}
    metrics = (data.get("fundamentals") or {}).get("metrics") or {}
    for key in ("revenue_growth", "earnings_growth", "gross_margins"):
        value = _to_float(metrics.get(key))
        if value is not None:
            facts[key] = {"raw_ratio": value, "display_percent": f"{value * 100:.1f}%"}
    for key in ("forward_pe", "trailing_pe", "price_to_sales"):
        value = _to_float(metrics.get(key))
        if value is not None:
            facts[key] = {"raw_value": value, "display_value": f"{value:.1f}"}

    technical = data.get("technical_analysis") or {}
    for key in ("current_price", "ma20", "ma50", "rsi14", "rsi_14", "macd", "macd_signal", "macd_histogram"):
        value = _to_float(technical.get(key))
        if value is not None:
            facts[key] = value

    ml = data.get("ml_research") or data.get("theme_ml_reference") or {}
    for key, target in (ml.get("targets") or {}).items():
        percent = _to_float((target or {}).get("probability_percent"))
        if percent is None:
            probability = _to_float((target or {}).get("probability"))
            percent = probability * 100 if probability is not None else None
        if percent is not None:
            facts[f"ml_{key}"] = f"{percent:.1f}%"
    return facts


def restore_immutable_report_numbers(*, kind: str, data: dict, report: str) -> str:
    """Repair supported labeled values if an LLM revision rescales them."""
    if kind != "single_stock":
        return report

    metrics = (data.get("fundamentals") or {}).get("metrics") or {}
    replacements = (
        ("revenue_growth", r"(營收成長(?:約|為)?\s*)([+-]?[\d,.]+)(\s*%)"),
        ("earnings_growth", r"(獲利成長(?:約|為)?\s*)([+-]?[\d,.]+)(\s*%)"),
        ("gross_margins", r"(毛利率(?:約|為)?\s*)([+-]?[\d,.]+)(\s*%)"),
    )
    repaired = report
    for key, pattern in replacements:
        raw = _to_float(metrics.get(key))
        if raw is None:
            continue
        expected = f"{raw * 100:.1f}"
        repaired = re.sub(
            pattern,
            lambda match, value=expected: f"{match.group(1)}{value}{match.group(3)}",
            repaired,
            count=1,
        )
    return repaired


def strip_internal_review_metadata(report: str) -> str:
    lines = [
        line
        for line in report.splitlines()
        if not any(term in line.lower() for term in INTERNAL_REVIEW_TERMS)
    ]
    return "\n".join(lines).strip()


def validate_llm_review(value: dict) -> dict:
    status = normalize_llm_review_status(value.get("status"))
    adjustment = value.get("confidence_adjustment", "none")
    if adjustment not in {"none", "lower"}:
        raise ValueError("LLM reviewer returned an invalid confidence adjustment.")
    raw_scores = value.get("quality_scores")
    if not isinstance(raw_scores, dict):
        raise ValueError("LLM reviewer did not return quality_scores.")
    quality_scores = {}
    for field in QUALITY_SCORE_FIELDS:
        score = raw_scores.get(field)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"LLM reviewer returned an invalid {field} score.")
        normalized_score = int(score)
        if normalized_score != score or not 1 <= normalized_score <= 5:
            raise ValueError(f"LLM reviewer returned an invalid {field} score.")
        quality_scores[field] = normalized_score
    risk_notes = _string_list(value.get("risk_notes"))
    suggested_fixes = _string_list(value.get("suggested_fixes"))
    low_fields = [
        field
        for field, score in quality_scores.items()
        if score < MIN_PASSING_QUALITY_SCORE
    ]
    if status is None:
        status = "needs_revision" if low_fields or risk_notes else "pass"
    if status == "pass" and (low_fields or risk_notes):
        status = "needs_revision"
        adjustment = "lower"
    if low_fields:
        risk_notes.append(
            "Quality score below the passing threshold: " + ", ".join(low_fields)
        )
        suggested_fixes.append(
            "Revise the report to raise every semantic quality dimension to at least 4/5."
        )
    return {
        "review_version": REPORT_REVIEW_VERSION,
        "status": status,
        "checks": [],
        "risk_notes": list(dict.fromkeys(risk_notes)),
        "confidence_adjustment": adjustment,
        "suggested_fixes": list(dict.fromkeys(suggested_fixes)),
        "reason": str(value.get("reason") or "LLM semantic review completed."),
        "quality_scores": quality_scores,
        "minimum_passing_score": MIN_PASSING_QUALITY_SCORE,
    }


def normalize_llm_review_status(value) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pass": "pass",
        "passed": "pass",
        "approved": "pass",
        "approve": "pass",
        "success": "pass",
        "ok": "pass",
        "needs_revision": "needs_revision",
        "need_revision": "needs_revision",
        "revision_required": "needs_revision",
        "requires_revision": "needs_revision",
        "revise": "needs_revision",
        "fail": "needs_revision",
        "failed": "needs_revision",
    }
    return aliases.get(normalized)


def parse_json_object(raw: str) -> dict:
    return parse_first_json_object(
        raw,
        error_message="LLM reviewer response must include a JSON object.",
    )


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


def get_revision_llm_client_from_env():
    if os.getenv("MARKET_AGENT_REPORT_REVIEW_PROVIDER", "openrouter").lower() != "openrouter":
        return None
    client = OpenRouterChatClient.from_env()
    if client is None:
        return None
    model = (
        os.getenv("MARKET_AGENT_REPORT_REVISER_MODEL", "").strip()
        or os.getenv("MARKET_AGENT_REPORT_WRITER_MODEL", "").strip()
        or os.getenv("MARKET_AGENT_LLM_MODEL", "").strip()
    )
    if model:
        client.model = model
    return client


def normalize_review_mode(value: str | None) -> str:
    normalized = str(value or "deterministic").strip().lower()
    return (
        normalized
        if normalized in {"deterministic", "hybrid", "semantic"}
        else "deterministic"
    )


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
        "backtest": ["風險提醒"],
        "theme": ["風險提醒"],
        "portfolio": ["風險提醒"],
    }.get(kind, [])
    for title in required:
        _check(checks, f"required_section:{title}", title in report, f"報告缺少必要段落：{title}。", f"補上「{title}」段落。")
    if kind == "backtest":
        has_performance_section = any(
            title in report for title in ("績效摘要", "訊號歷史統計")
        )
        _check(
            checks,
            "required_section:績效摘要",
            has_performance_section,
            "報告缺少必要段落：績效摘要或訊號歷史統計。",
            "補上「績效摘要」或「訊號歷史統計」段落。",
        )
        _check(
            checks,
            "backtest_no_unsupported_ml_reference",
            "ML Reference" not in report,
            "回測 payload 沒有 ML target，不應出現 ML Reference。",
            "移除沒有結構化 ML target 支持的 ML Reference 段落。",
        )
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
    if holding:
        entry_only_conclusions = (
            "目前結論為「暫不進場」",
            "目前結論為「等待更好價格」",
            "目前結論為「可列入觀察」",
            "目前結論為「觀察回踩是否有效」",
            "目前結論為「降低進場信心」",
        )
        has_entry_only_conclusion = any(
            conclusion in report for conclusion in entry_only_conclusions
        )
        _check(
            checks,
            "holding_conclusion_matches_exit_signal",
            not has_entry_only_conclusion,
            "持有問題仍使用只適用於進場的結論。",
            "依 exit_signal 改用續抱觀察、提高觀察、評估減碼或出場風險偏高。",
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


def _review_internal_metadata(report: str, checks: list[dict]) -> None:
    leaked = [term for term in INTERNAL_REVIEW_TERMS if term in report.lower()]
    _check(
        checks,
        "no_internal_review_metadata",
        not leaked,
        "報告不應揭露 reviewer 或內部品質檢查欄位。",
        "直接修正報告內容，不要描述 deterministic review、confidence adjustment 或修訂流程。",
    )


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
    if kind == "single_stock":
        _review_fundamental_numbers(data, report, checks)
        _review_technical_numbers(data, report, checks)
    if kind == "backtest":
        metrics = data.get("metrics") or {}
        total = metrics.get("total_trades")
        if total is not None:
            _check(checks, "backtest_trade_count", str(total) in report, "回測報告未保留總交易次數。", "補回 Structured Data 的 total_trades。")


def _review_fundamental_numbers(data: dict, report: str, checks: list[dict]) -> None:
    metrics = (data.get("fundamentals") or {}).get("metrics") or {}
    fields = (
        ("revenue_growth", "營收成長", r"營收成長[^\n\d+-]{0,24}(?:\*\*)?([+-]?[\d,.]+)\s*%(?:\*\*)?"),
        ("earnings_growth", "獲利成長", r"獲利成長[^\n\d+-]{0,24}(?:\*\*)?([+-]?[\d,.]+)\s*%(?:\*\*)?"),
        ("gross_margins", "毛利率", r"毛利率[^\n\d+-]{0,24}(?:\*\*)?([+-]?[\d,.]+)\s*%(?:\*\*)?"),
    )
    for key, label, pattern in fields:
        raw = _to_float(metrics.get(key))
        if raw is None:
            continue
        match = re.search(pattern, report)
        actual = _to_float(match.group(1).replace(",", "")) if match else None
        expected = round(raw * 100, 1)
        _check(
            checks,
            f"fundamental_number_matches:{key}",
            actual is not None and abs(actual - expected) <= 0.05,
            f"{label}百分比未保留結構化資料的比例換算結果 {expected:.1f}%。",
            f"將{label}顯示為 {expected:.1f}%，不可把原始 ratio 直接加上百分號。",
        )


def _review_technical_numbers(data: dict, report: str, checks: list[dict]) -> None:
    technical = data.get("technical_analysis") or {}
    fields = (
        ("ma20", "MA20", r"MA20(?:\*\*)?\s*(?:約|為)?\s*[:：]?\s*(?:\*\*)?\$?([\d,.]+)(?:\*\*)?"),
        ("ma50", "MA50", r"MA50(?:\*\*)?\s*(?:約|為)?\s*[:：]?\s*(?:\*\*)?\$?([\d,.]+)(?:\*\*)?"),
        ("macd_histogram", "MACD histogram", r"(?:histogram|柱狀圖)(?:\*\*)?\s*(?:(?:為|[:：])\s*)?(?:\*\*)?([+-]?[\d,.]+)(?:\*\*)?"),
    )
    for key, label, pattern in fields:
        expected = _to_float(technical.get(key))
        if expected is None:
            continue
        match = re.search(pattern, report, flags=re.IGNORECASE)
        actual = _to_float(match.group(1).replace(",", "")) if match else None
        tolerance = 0.51 if key in {"ma20", "ma50"} else 0.00011
        _check(
            checks,
            f"technical_number_matches:{key}",
            actual is not None and abs(actual - expected) <= tolerance,
            f"報告中的 {label} 未保留 Structured Data 數值。",
            f"使用 Structured Data 的 {label}，不可由 LLM 重新計算。",
        )


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "quality_scores": review.get("quality_scores", {}),
    }


def _result(
    *,
    report,
    deterministic,
    history,
    mode_used,
    iterations,
    max_iterations,
    client=None,
    semantic_review=None,
    fallback_reason=None,
):
    review = {
        **deterministic,
        "mode_used": mode_used,
        "iterations": iterations,
        "max_iterations": max_iterations,
        "provider": getattr(client, "provider", None),
        "model": getattr(client, "model", None),
        "fallback_used": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "history": history,
        "semantic_quality": _semantic_quality_summary(semantic_review),
    }
    return {"report": report, "review": review}


def _semantic_quality_summary(review: dict | None) -> dict:
    if not isinstance(review, dict):
        return {
            "status": "not_run",
            "quality_scores": {},
            "minimum_passing_score": MIN_PASSING_QUALITY_SCORE,
            "reason": None,
        }
    return {
        "status": review.get("status", "unknown"),
        "quality_scores": review.get("quality_scores", {}),
        "minimum_passing_score": MIN_PASSING_QUALITY_SCORE,
        "reason": review.get("reason"),
    }


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
