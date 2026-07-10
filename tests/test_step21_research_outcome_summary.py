from research_logging import classify_research_outcome_quality
from pathlib import Path
from scripts.build_research_outcome_summary import (
    build_research_outcome_summary_markdown,
    build_research_outcome_summary_report,
)
from scripts.log_daily_research_fixtures import build_daily_research_fixture_markdown


def test_quality_rules_mark_caution_signal_good_when_it_avoids_drawdown():
    result = classify_research_outcome_quality(
        {
            "outcome_status": "computed",
            "conclusion": "暫不進場",
            "return_pct": -0.02,
            "max_drawdown_pct": -0.06,
        }
    )

    assert result["quality"] == "good"
    assert result["quality_reason"] == "caution_signal_avoided_drawdown"


def test_quality_rules_mark_positive_signal_poor_when_drawdown_is_large():
    result = classify_research_outcome_quality(
        {
            "outcome_status": "computed",
            "conclusion": "可列入觀察",
            "return_pct": -0.01,
            "max_drawdown_pct": -0.07,
        }
    )

    assert result["quality"] == "poor"
    assert result["quality_reason"] == "positive_signal_had_large_drawdown"


def test_quality_rules_mark_reduce_signal_good_when_loss_follows():
    result = classify_research_outcome_quality(
        {
            "outcome_status": "computed",
            "conclusion": "觀察回踩是否有效",
            "exit_signal": "reduce",
            "return_pct": -0.01,
            "max_drawdown_pct": -0.02,
        }
    )

    assert result["quality"] == "neutral_to_good"
    assert result["quality_reason"] == "exit_signal_warned_before_loss"


def test_research_outcome_summary_groups_quality_and_conclusion():
    report = build_research_outcome_summary_report(
        [
            {
                "ticker": "MU",
                "outcome_status": "computed",
                "conclusion": "暫不進場",
                "horizon_trading_days": 5,
                "return_pct": -0.02,
                "max_drawdown_pct": -0.06,
            },
            {
                "ticker": "MU",
                "outcome_status": "computed",
                "conclusion": "可列入觀察",
                "horizon_trading_days": 5,
                "return_pct": -0.01,
                "max_drawdown_pct": -0.07,
            },
        ]
    )

    assert report["quality_counts"] == {"good": 1, "poor": 1}
    assert report["conclusion_summary"]["暫不進場"]["count"] == 1
    markdown = build_research_outcome_summary_markdown(report)
    assert "Research Outcome Summary" in markdown
    assert "quality=good" in markdown


def test_daily_research_fixture_markdown_combines_reports_with_separators():
    markdown = build_daily_research_fixture_markdown(
        {
            "generated_at": "2026-07-10T00:00:00+00:00",
            "status": "success",
            "fixture_count": 2,
            "results": [
                {
                    "status": "success",
                    "query": "MU 現在適合進場嗎",
                    "report": "研究摘要\n內容 A",
                },
                {
                    "status": "success",
                    "query": "記憶體類股現在適合進場觀察嗎",
                    "report": "主題摘要\n內容 B",
                },
            ],
        }
    )

    assert "MU 現在適合進場嗎" in markdown
    assert "記憶體類股現在適合進場觀察嗎" in markdown
    assert "\n---\n" in markdown


def test_weekly_research_fixture_workflow_contains_all_extended_questions():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "weekly-research-fixtures.yml"
    ).read_text(encoding="utf-8")

    assert 'cron: "30 2 * * 6"' in workflow
    assert "NVDA 現在適合進場嗎" in workflow
    assert "AAPL 現在適合進場嗎" in workflow
    assert "半導體類股現在適合進場觀察嗎" in workflow
    assert "MU 放量策略以前表現怎麼樣" in workflow
    assert "MU 拉回策略以前表現怎麼樣" in workflow
