import json

from agent.report_review import review_and_revise_report, run_deterministic_review
from agent.reporting import build_report


VALID_THEME_REPORT = "主題研究摘要\n目前訊號混合。\n\n風險提醒\n本摘要不構成投資建議。"


class SequenceClient:
    provider = "openrouter"
    model = "review-test"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, system_prompt, user_prompt):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if not self.responses:
            raise AssertionError("Unexpected extra LLM call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def llm_review(status="needs_revision", scores=None):
    scores = scores or {
        "query_relevance": 5,
        "evidence_consistency": 5,
        "risk_balance": 5,
        "clarity": 5,
        "hallucination_safety": 5,
        "overall_quality": 5,
    }
    return json.dumps(
        {
            "status": status,
            "quality_scores": scores,
            "risk_notes": [] if status == "pass" else ["語氣過度確定"],
            "suggested_fixes": [] if status == "pass" else ["改成研究觀察語氣"],
            "confidence_adjustment": "none" if status == "pass" else "lower",
            "reason": "semantic review",
        },
        ensure_ascii=False,
    )


def test_deterministic_review_checks_material_report_contracts():
    data = {
        "status": "success",
        "question_type": "holding_exit",
        "ml_reference_trust": {"status": "reduced_trust"},
        "data_freshness": {"overall": "warning"},
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析", "內容", "技術面分析", "內容",
            "新聞面分析", "內容", "ML Reference", "內容", "綜合評估", "內容",
            "風險提醒", "本摘要不構成投資建議。",
        ]
    )
    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}
    assert result["status"] == "needs_revision"
    assert "holding_section_matches_question" in failed
    assert "ml_reduced_trust_disclosed" in failed
    assert "freshness_warning_disclosed" in failed


def test_passing_report_does_not_call_llm():
    client = SequenceClient([AssertionError("LLM should not run")])
    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report=VALID_THEME_REPORT,
        mode="hybrid",
        llm_client=client,
    )
    assert result["review"]["status"] == "pass"
    assert result["review"]["iterations"] == 0
    assert client.calls == []


def test_hybrid_review_revises_and_stops_after_pass():
    client = SequenceClient([llm_review(), VALID_THEME_REPORT, llm_review("pass")])
    result = review_and_revise_report(
        kind="theme",
        data={
            "status": "success",
            "analyst_consensus": {"has_conflict": True, "consensus": "mixed"},
        },
        report="主題摘要\n現在一定要買。\n\n風險提醒\n不構成投資建議。",
        mode="hybrid",
        llm_client=client,
    )
    assert result["report"] == VALID_THEME_REPORT
    assert result["review"]["status"] == "pass"
    assert result["review"]["iterations"] == 1
    assert len(client.calls) == 3
    assert "analyst_consensus" in client.calls[0]["user"]


def test_review_loop_is_capped_at_three_iterations_and_seven_calls():
    bad_report = "主題摘要\n保證獲利。\n\n風險提醒\n不構成投資建議。"
    responses = []
    for _ in range(3):
        responses.extend([llm_review(), bad_report])
    responses.append(llm_review())
    client = SequenceClient(responses)
    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report=bad_report,
        mode="hybrid",
        llm_client=client,
        max_iterations=3,
    )
    assert result["review"]["status"] == "needs_revision"
    assert result["review"]["iterations"] == 3
    assert result["review"]["fallback_used"] is True
    assert len(client.calls) == 7


def test_llm_failure_preserves_original_report_and_review_warning():
    client = SequenceClient([RuntimeError("provider unavailable")])
    original = "主題摘要\n應立即買進。\n\n風險提醒\n不構成投資建議。"
    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report=original,
        mode="hybrid",
        llm_client=client,
    )
    assert result["report"] == original
    assert result["review"]["status"] == "needs_revision"
    assert result["review"]["fallback_used"] is True
    assert "provider unavailable" in result["review"]["fallback_reason"]


def test_deterministic_review_verifies_structured_ml_probabilities():
    data = {
        "status": "success",
        "ml_research": {
            "status": "success",
            "targets": {
                "up_5d": {"probability_percent": 53.8},
                "up_10d": {"probability_percent": 51.6},
                "up_20d": {"probability_percent": 50.4},
                "large_drop_20d": {"probability_percent": 69.2},
            },
        },
    }
    report = "研究摘要\n摘要\n基本面分析\n內容\n技術面分析\n內容\n新聞面分析\n內容\nML Reference\n53.8%、51.6%、50.4%。\n綜合評估\n內容\n風險提醒\n不構成投資建議。"
    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}
    assert "ml_number_present:large_drop_20d" in failed


def test_holding_question_is_detected_from_query_when_question_type_is_absent():
    data = {"status": "success", "query": "MU 如果我已經持有，現在要不要減碼"}
    result = run_deterministic_review(kind="single_stock", data=data, report="研究摘要\n基本面分析\n技術面分析\n新聞面分析\nML Reference\n綜合評估\n風險提醒\n不構成投資建議。")
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}
    assert "holding_section_matches_question" in failed


def test_holding_review_rejects_entry_only_conclusion():
    data = {"status": "success", "question_type": "holding_exit"}
    report = "\n".join(
        [
            "研究摘要",
            "MU目前結論為「暫不進場」。",
            "基本面分析",
            "test",
            "技術面分析",
            "test",
            "新聞面分析",
            "test",
            "ML Reference",
            "test",
            "持有風險 / 出場觀察",
            "目前 exit signal 為「reduce」。",
            "綜合評估",
            "test",
            "風險提醒",
            "不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert "holding_conclusion_matches_exit_signal" in failed


def test_build_report_exposes_review_in_result_and_structured_data():
    data = {"status": "no_price_data", "message": "price data unavailable"}
    result = build_report(kind="single_stock", data=data, analyst_mode="rule_based")
    assert result["review"]["review_version"] == "report_review_v2"
    assert data["report_review"] == result["review"]


def test_semantic_mode_reviews_even_when_deterministic_checks_pass():
    client = SequenceClient([llm_review("pass")])

    result = review_and_revise_report(
        kind="theme",
        data={"status": "success", "query": "記憶體類股現在適合觀察嗎"},
        report=VALID_THEME_REPORT,
        mode="semantic",
        llm_client=client,
    )

    assert result["review"]["status"] == "pass"
    assert result["review"]["mode_used"] == "semantic"
    assert result["review"]["semantic_quality"]["status"] == "pass"
    assert result["review"]["semantic_quality"]["quality_scores"]["overall_quality"] == 5
    assert len(client.calls) == 1
    assert "記憶體類股現在適合觀察嗎" in client.calls[0]["user"]


def test_semantic_review_rejects_pass_status_when_any_score_is_below_four():
    low_scores = {
        "query_relevance": 3,
        "evidence_consistency": 5,
        "risk_balance": 5,
        "clarity": 5,
        "hallucination_safety": 5,
        "overall_quality": 4,
    }
    client = SequenceClient(
        [llm_review("pass", low_scores), VALID_THEME_REPORT, llm_review("pass")]
    )

    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report=VALID_THEME_REPORT,
        mode="semantic",
        llm_client=client,
    )

    assert result["review"]["status"] == "pass"
    assert result["review"]["iterations"] == 1
    first_semantic = next(
        entry for entry in result["review"]["history"] if entry["stage"] == "llm_review"
    )
    assert first_semantic["status"] == "needs_revision"


def test_semantic_mode_fails_closed_when_review_client_is_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report=VALID_THEME_REPORT,
        mode="semantic",
        llm_client=None,
    )

    assert result["review"]["status"] == "needs_revision"
    assert result["review"]["fallback_used"] is True
    assert result["review"]["semantic_quality"]["status"] == "not_run"
