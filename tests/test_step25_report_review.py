import json

from agent.fixed_single_stock_report import build_risk_reminder
from agent.report_review import (
    build_review_context,
    restore_immutable_report_numbers,
    review_and_revise_report,
    run_deterministic_review,
    strip_internal_review_metadata,
    validate_llm_review,
)
from agent.reporting import (
    apply_required_report_sections,
    build_report,
    normalize_single_stock_section_titles,
)


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


def test_review_uses_separate_lower_cost_revision_client():
    reviewer = SequenceClient([llm_review(), llm_review("pass")])
    reviser = SequenceClient([VALID_THEME_REPORT])
    result = review_and_revise_report(
        kind="theme",
        data={"status": "success"},
        report="主題摘要\n現在一定要買。\n\n風險提醒\n不構成投資建議。",
        mode="hybrid",
        llm_client=reviewer,
        revision_llm_client=reviser,
        max_iterations=1,
    )

    assert result["review"]["status"] == "pass"
    assert len(reviewer.calls) == 2
    assert len(reviser.calls) == 1


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


def test_required_report_sections_restore_missing_theme_ml_probabilities():
    data = {
        "status": "success",
        "theme_ml_reference": {
            "status": "success",
            "targets": {
                "up_5d": {
                    "probability_percent": 44.8,
                    "signal_label": "slightly bearish",
                    "signal_quality": "low",
                },
                "up_10d": {
                    "probability_percent": 45.1,
                    "signal_label": "slightly bearish",
                    "signal_quality": "low",
                },
                "up_20d": {
                    "probability_percent": 53.0,
                    "signal_label": "unclear direction",
                    "signal_quality": "low",
                },
                "large_drop_20d": {
                    "probability_percent": 76.0,
                    "signal_label": "high large-drop risk",
                    "signal_quality": "medium",
                },
            },
        },
    }
    report = "\n".join(
        [
            "## 研究摘要",
            "內容",
            "## ML Reference",
            "5 日與 10 日方向訊號偏弱。",
            "20 日上漲機率為 53.0%。",
            "20 日大跌風險為 76.0%。",
            "## 風險提醒",
            "不構成投資建議。",
        ]
    )

    updated = apply_required_report_sections(kind="theme", data=data, report=report)
    review = run_deterministic_review(kind="theme", data=data, report=updated)

    assert "44.8%" in updated
    assert "45.1%" in updated
    assert review["status"] == "pass"


def test_llm_review_normalizes_status_aliases():
    value = json.loads(llm_review("needs_revision"))
    value["status"] = "revision_required"

    normalized = validate_llm_review(value)

    assert normalized["status"] == "needs_revision"


def test_llm_review_derives_missing_status_from_valid_scores():
    value = json.loads(llm_review("pass"))
    value.pop("status")

    normalized = validate_llm_review(value)

    assert normalized["status"] == "pass"


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
    assert result["review"]["review_version"] == "report_review_v3"
    assert data["report_review"] == result["review"]


def test_deterministic_review_rejects_rescaled_fundamental_percentages():
    data = {
        "status": "success",
        "fundamentals": {
            "status": "success",
            "metrics": {
                "revenue_growth": 3.457,
                "earnings_growth": 13.685,
                "gross_margins": 0.72569,
            },
        },
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析",
            "營收成長約 3.457%。獲利成長約 13.685%。毛利率約 72.6%。",
            "技術面分析", "內容", "新聞面分析", "內容", "ML Reference", "內容",
            "綜合評估", "內容", "風險提醒", "不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert "fundamental_number_matches:revenue_growth" in failed
    assert "fundamental_number_matches:earnings_growth" in failed
    assert "fundamental_number_matches:gross_margins" not in failed


def test_deterministic_review_accepts_ratio_to_percent_conversion():
    data = {
        "status": "success",
        "fundamentals": {
            "status": "success",
            "metrics": {
                "revenue_growth": 3.457,
                "earnings_growth": 13.685,
                "gross_margins": 0.72569,
            },
        },
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析",
            "資料來源回報的營收成長約 345.7%（期間定義依 provider）。"
            "資料來源回報的獲利成長約 1368.5%（期間定義依 provider）。"
            "毛利率約 72.6%。",
            "技術面分析", "內容", "新聞面分析", "內容", "ML Reference", "內容",
            "綜合評估", "內容", "風險提醒", "不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert not {code for code in failed if code.startswith("fundamental_number_matches:")}


def test_deterministic_review_accepts_markdown_bold_immutable_numbers():
    data = {
        "status": "success",
        "fundamentals": {
            "metrics": {
                "revenue_growth": 3.457,
                "earnings_growth": 13.685,
                "gross_margins": 0.72569,
            },
        },
        "technical_analysis": {
            "ma20": 1009.92,
            "ma50": 937.55,
            "macd_histogram": -28.5724,
        },
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析",
            "- **營收成長**：**345.7%**",
            "- **獲利成長**：**1368.5%**",
            "- **毛利率**：**72.6%**",
            "技術面分析",
            "現價低於 MA20 **1009.92**、MA50 **937.55**。",
            "MACD Histogram 為 **-28.5724**。",
            "新聞面分析", "內容", "ML Reference", "內容",
            "綜合評估", "內容", "風險提醒", "不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert not {code for code in failed if "_number_matches:" in code}


def test_deterministic_review_accepts_natural_bold_holding_report_numbers():
    data = {
        "status": "success",
        "fundamentals": {
            "metrics": {
                "revenue_growth": 3.457,
                "earnings_growth": 13.685,
                "gross_margins": 0.72569,
            },
        },
        "technical_analysis": {"ma20": 996.67, "ma50": 943.55, "macd_histogram": -20.7139},
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析",
            "營收成長為正（**345.7%**）。",
            "獲利成長為正（**1368.5%**）。",
            "毛利率相對較高（**72.6%**）。",
            "技術面分析",
            "現價低於 MA20 **996.67**，MA50 為 **943.55**。",
            "MACD 柱狀圖為 **-20.7139**，短線動能轉弱。",
            "新聞面分析", "內容", "ML Reference", "內容",
            "綜合評估", "內容", "風險提醒", "不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="single_stock", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert not {code for code in failed if "_number_matches:" in code}


def test_review_context_includes_news_events_used_by_report_writer():
    data = {
        "news_analysis": {"summary": {"sentiment": "positive"}},
        "agent_outputs": {
            "news": {
                "news_events_summary": {
                    "representative_events": [
                        {"title": "Supported event", "sentiment": "negative"}
                    ]
                }
            }
        },
    }

    context = build_review_context(data)

    assert context["news_summary"]["sentiment"] == "positive"
    assert context["news_events_summary"]["representative_events"][0]["title"] == "Supported event"


def test_theme_review_context_matches_writer_news_aggregation():
    data = {
        "theme_key": "memory",
        "theme_name": "記憶體",
        "results": [
            {
                "status": "success",
                "analysis": {
                    "news_analysis": {
                        "summary": {
                            "total_items": 5,
                            "high_importance_count": 1,
                            "sentiment": "positive",
                            "top_topics": {"product_demand": 3},
                        }
                    },
                    "fundamentals": {
                        "status": "success",
                        "summary": {"stance": "positive", "positives": ["growth"], "risks": []},
                    },
                },
            }
        ],
    }

    context = build_review_context(data)

    assert context["theme_news_summary"]["total_items"] == 5
    assert context["theme_news_summary"]["sentiment_counts"] == {"positive": 1}
    assert context["news_summary"] == context["theme_news_summary"]
    assert context["theme_fundamental_summary"]["stance_counts"] == {"positive": 1}


def test_holding_report_injects_material_negative_news_risk():
    title = "Micron Faces Antitrust Lawsuit Over AI Memory Production Cuts"
    data = {
        "status": "success",
        "query": "MU 如果我已經持有，現在要不要減碼",
        "question_type": "holding_exit",
        "exit_signal": {"status": "success", "exit_signal": "reduce"},
        "agent_outputs": {
            "news": {
                "news_events_summary": {
                    "representative_events": [
                        {
                            "title": title,
                            "source": "simplywall.st",
                            "published_at": "2026-06-30T00:00:00+00:00",
                            "sentiment": "negative",
                            "topic": "risk_event",
                            "importance": "high",
                        }
                    ]
                }
            }
        },
    }
    report = "\n".join(
        [
            "## 研究摘要", "內容", "## 基本面分析", "內容",
            "## 技術面分析", "內容", "## 新聞面分析", "risk_event 2 則。",
            "## ML Reference", "內容", "## 持有風險 / 出場觀察", "內容",
            "## 綜合評估", "內容", "## 風險提醒", "不構成投資建議。",
        ]
    )

    updated = apply_required_report_sections(kind="single_stock", data=data, report=report)

    assert title in updated
    assert "不能單獨決定減碼" in updated


def test_backtest_report_removes_unsupported_ml_reference_section():
    report = "\n".join(
        [
            "## 績效摘要", "勝率 53%。",
            "## ML Reference", "沒有結構化資料支持的 ML 描述。",
            "## 綜合評估", "歷史優勢有限。",
            "## 風險提醒", "不構成投資建議。",
        ]
    )

    updated = apply_required_report_sections(
        kind="backtest",
        data={"status": "success"},
        report=report,
    )

    assert "ML Reference" not in updated
    assert "沒有結構化資料支持的 ML 描述" not in updated
    assert "綜合評估" in updated


def test_backtest_review_accepts_signal_history_statistics_section():
    data = {"status": "success", "metrics": {"total_trades": 222}}
    report = "\n".join(
        [
            "MU 策略回測摘要",
            "訊號歷史統計",
            "- 非重疊交易次數：222",
            "風險提醒",
            "本報告不構成投資建議。",
        ]
    )

    result = run_deterministic_review(kind="backtest", data=data, report=report)
    failed = {item["code"] for item in result["checks"] if item["status"] == "fail"}

    assert "required_section:績效摘要" not in failed


def test_semantic_prompt_defines_evidence_scopes_and_immutable_facts():
    client = SequenceClient([llm_review("pass")])
    data = {
        "status": "success",
        "query": "MU 現在適合進場嗎",
        "evidence_quality": {"level": "medium"},
        "fundamentals": {
            "status": "success",
            "metrics": {"revenue_growth": 3.457},
        },
        "ml_research": {
            "status": "success",
            "return_reference": {"evidence_quality": "high"},
        },
        "ml_reference_trust": {"status": "reduced_trust"},
    }
    report = "\n".join(
        [
            "研究摘要", "摘要", "基本面分析",
            "資料來源回報的營收成長約 345.7%（期間定義依 provider）。",
            "技術面分析", "內容", "新聞面分析", "內容",
            "ML Reference", "降低信任，請保守解讀。",
            "綜合評估", "整體證據品質為 medium。",
            "風險提醒", "不構成投資建議。",
        ]
    )

    result = review_and_revise_report(
        kind="single_stock",
        data=data,
        report=report,
        mode="semantic",
        llm_client=client,
    )

    prompt_payload = json.loads(client.calls[0]["user"])
    assert result["review"]["status"] == "pass"
    assert prompt_payload["structured_context"]["quality_scope_definitions"]
    assert prompt_payload["structured_context"]["immutable_facts"]["revenue_growth"]["display_percent"] == "345.7%"


def test_llm_rescaled_fundamental_percentages_are_restored():
    data = {
        "fundamentals": {
            "metrics": {
                "revenue_growth": 3.457,
                "earnings_growth": 13.685,
                "gross_margins": 0.72569,
            }
        }
    }
    revised = "營收成長約 3.457%。獲利成長約 13.685%。毛利率約 0.72569%。"

    repaired = restore_immutable_report_numbers(
        kind="single_stock",
        data=data,
        report=revised,
    )

    assert "營收成長約 345.7%" in repaired
    assert "獲利成長約 1368.5%" in repaired
    assert "毛利率約 72.6%" in repaired


def test_internal_review_metadata_is_removed_from_report():
    report = "\n".join(
        [
            "績效摘要",
            "結果偏正向。",
            "研究信心已依 deterministic_review 的 confidence_adjustment: lower 下調。",
            "風險提醒",
            "不構成投資建議。",
        ]
    )

    cleaned = strip_internal_review_metadata(report)

    assert "deterministic_review" not in cleaned
    assert "confidence_adjustment" not in cleaned
    assert "結果偏正向" in cleaned


def test_single_stock_section_aliases_are_normalized():
    report = "\n".join(
        [
            "## 研究總結",
            "## 基本面觀察",
            "## 技術面觀察",
            "## 新聞面觀察",
            "## ML Reference",
            "## 持有部位風險評估",
            "## 多面向整合",
            "## 資料與風險提醒",
        ]
    )

    normalized = normalize_single_stock_section_titles(report)

    for title in (
        "研究摘要",
        "基本面分析",
        "技術面分析",
        "新聞面分析",
        "持有風險 / 出場觀察",
        "綜合評估",
        "風險提醒",
    ):
        assert title in normalized


def test_entry_report_discloses_material_risk_without_holding_section():
    reminder = build_risk_reminder(
        {
            "question_type": "entry_or_research",
            "exit_signal": {
                "status": "success",
                "exit_signal": "exit",
                "weakening_signal_20d": "high",
            },
            "data_freshness": {
                "warnings": [{"source": "ml_training_data"}],
            },
        }
    )

    assert "技術轉弱程度偏高" in reminder
    assert "只作為進場風險提醒" in reminder
    assert "ML 資料新鮮度提醒會降低 ML Reference 信任度" in reminder
    assert "持有風險 / 出場觀察" not in reminder


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
