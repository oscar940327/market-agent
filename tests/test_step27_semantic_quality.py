from pathlib import Path

from scripts.log_daily_research_fixtures import (
    build_agent_flow_summary,
    build_daily_research_fixture_markdown,
    build_daily_research_fixture_report,
    build_fixture_failure_diagnostics,
)


def passing_review(*, overall=5, iterations=0):
    return {
        "status": "pass",
        "provider": "openrouter",
        "model": "openai/gpt-5.4-mini",
        "iterations": iterations,
        "risk_notes": [],
        "semantic_quality": {
            "status": "pass",
            "quality_scores": {
                "query_relevance": 5,
                "evidence_consistency": 5,
                "risk_balance": 4,
                "clarity": 4,
                "hallucination_safety": 5,
                "overall_quality": overall,
            },
            "reason": "Report is supported by the structured context.",
        },
    }


def test_fixture_failure_diagnostics_exposes_reason_scores_and_checks():
    lines = build_fixture_failure_diagnostics(
        {
            "report_review": {
                "checks": [
                    {"code": "technical_number_matches:ma50", "status": "fail"}
                ],
                "fallback_reason": "Maximum review iterations reached.",
                "semantic_quality": {
                    "reason": "News stance is inconsistent.",
                    "quality_scores": {"evidence_consistency": 3},
                },
            }
        }
    )

    assert "semantic_reason=News stance is inconsistent." in lines
    assert "quality_scores=evidence_consistency:3" in lines
    assert "failed_checks=technical_number_matches:ma50" in lines
    assert "review_fallback_reason=Maximum review iterations reached." in lines


def test_fixture_report_aggregates_semantic_quality_scores():
    report = build_daily_research_fixture_report(
        [
            {
                "status": "success",
                "query": "MU 現在適合進場嗎",
                "report": "研究摘要\n內容",
                "report_review": passing_review(overall=5),
            },
            {
                "status": "success",
                "query": "記憶體類股現在適合觀察嗎",
                "report": "主題摘要\n內容",
                "report_review": passing_review(overall=4, iterations=1),
            },
        ]
    )

    assert report["status"] == "success"
    assert report["report_version"] == "daily_research_fixture_report_v2"
    assert report["quality_summary"]["reviewed_count"] == 2
    assert report["quality_summary"]["passed_count"] == 2
    assert report["quality_summary"]["average_scores"]["overall_quality"] == 4.5


def test_fixture_markdown_exposes_review_model_scores_and_iterations():
    report = build_daily_research_fixture_report(
        [
            {
                "status": "success",
                "query": "MU 現在適合進場嗎",
                "report": "研究摘要\n內容",
                "report_review": passing_review(iterations=1),
            }
        ]
    )

    markdown = build_daily_research_fixture_markdown(report)

    assert "品質審查" in markdown
    assert "openai/gpt-5.4-mini" in markdown
    assert "overall_quality 5/5" in markdown
    assert "修訂次數：1" in markdown


def test_quality_failure_makes_fixture_report_partial_but_keeps_report_visible():
    review = passing_review()
    review["status"] = "needs_revision"
    review["risk_notes"] = ["結論沒有回答原始問題。"]
    review["semantic_quality"]["status"] = "needs_revision"
    report = build_daily_research_fixture_report(
        [
            {
                "status": "quality_failed",
                "query": "MU 現在適合進場嗎",
                "report": "研究摘要\n最後一版內容",
                "report_review": review,
            }
        ]
    )

    markdown = build_daily_research_fixture_markdown(report)

    assert report["status"] == "partial_success"
    assert report["quality_summary"]["failed_count"] == 1
    assert "品質審查未通過" in markdown
    assert "最後一版內容" in markdown
    assert "結論沒有回答原始問題" in markdown


def test_fixture_workflows_use_cost_aware_review_policy():
    root = Path(__file__).resolve().parents[1]
    expected_modes = {
        "daily-research-fixtures.yml": "hybrid",
        "weekly-research-fixtures.yml": "semantic",
    }
    for name, mode in expected_modes.items():
        workflow = (root / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )
        assert f"MARKET_AGENT_REPORT_REVIEW_MODE: {mode}" in workflow
        assert "MARKET_AGENT_REPORT_REVIEW_MODEL: anthropic/claude-sonnet-4.6" in workflow
        assert "MARKET_AGENT_REPORT_REVISER_MODEL: openai/gpt-5.4-mini" in workflow
        assert 'MARKET_AGENT_REPORT_REVIEW_MAX_ITERATIONS: "1"' in workflow


def test_fixture_markdown_exposes_agent_flow_status():
    report = build_daily_research_fixture_report(
        [
            {
                "status": "success",
                "query": "MU 現在適合進場嗎",
                "report": "研究摘要\n內容",
                "report_review": passing_review(),
                "agent_flow": {
                    "label": "LLM",
                    "mode_used": "llm",
                    "fallback_used": False,
                },
            }
        ]
    )

    markdown = build_daily_research_fixture_markdown(report)

    assert "Agent Flow: LLM" in markdown


def test_agent_flow_summary_maps_llm_fixed_and_fallback():
    assert build_agent_flow_summary({"mode_used": "llm"})["label"] == "LLM"
    assert build_agent_flow_summary({"mode_used": "fixed"})["label"] == "Fixed"
    assert build_agent_flow_summary(
        {
            "mode_used": "fixed_fallback",
            "fallback_used": True,
            "fallback_reason": "tool_error",
        }
    )["label"] == "Fallback"
