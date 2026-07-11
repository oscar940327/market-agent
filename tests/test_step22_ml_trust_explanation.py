from agent.fixed_single_stock_report import build_ml_reference
from agent.ml_reference_trust import build_ml_reference_trust
from agent.reporting import enforce_theme_ml_reference_trust


def make_ml_research(*, source_type="saved_daily_prediction", freshness="fresh"):
    return {
        "status": "success",
        "model_version": "baseline_v1",
        "source": {
            "type": source_type,
            "prediction_freshness": freshness,
            "model_version": "baseline_v1",
            "reason": "saved_prediction_not_usable:ready/missing",
        },
        "targets": {
            "up_5d": {"signal_quality": "medium"},
            "up_10d": {"signal_quality": "medium"},
            "up_20d": {"signal_quality": "medium"},
            "large_drop_20d": {"signal_quality": "medium"},
        },
        "return_reference": {
            "sample_size": 120,
            "evidence_quality": "high",
        },
        "return_model": {
            "status": "success",
            "targets": {
                "forward_return_5d": {"model_quality": "high"},
                "forward_return_10d": {"model_quality": "high"},
                "forward_return_20d": {"model_quality": "high"},
                "max_drop_20d": {"model_quality": "high"},
            },
        },
    }


def test_normal_trust_explanation_shows_supporting_evidence():
    trust = build_ml_reference_trust(
        make_ml_research(),
        model_policy={"status": "normal", "model_version": "baseline_v1"},
    )

    explanation = trust["explanation"]
    assert trust["status"] == "normal"
    assert explanation["status"] == "normal"
    assert explanation["reason_codes"] == []
    assert {item["code"] for item in explanation["supports"]} == {
        "prediction_fresh",
        "historical_sample_available",
    }


def test_reduced_trust_explanation_combines_calibration_signal_and_downside_reasons():
    ml_research = make_ml_research()
    ml_research["targets"]["up_20d"]["signal_quality"] = "low"
    ml_research["return_model"]["targets"]["forward_return_20d"][
        "model_quality"
    ] = "low"
    ml_research["downside_risk_overlay"] = {"active": True}

    trust = build_ml_reference_trust(
        ml_research,
        model_policy={
            "status": "reduced_trust",
            "model_version": "baseline_v1",
            "source": "test_policy",
            "computed_outcomes": 1000,
            "calibration_findings": 4,
            "candidate_promoted": False,
        },
    )

    explanation = trust["explanation"]
    assert trust["status"] == "reduced_trust"
    assert {
        "up_20d_signal_quality_low",
        "return_model_quality_limited",
        "model_health_reduced_trust",
        "calibration_warning",
        "candidate_not_promoted",
        "downside_overlay_active",
    }.issubset(set(explanation["reason_codes"]))
    assert explanation["source"]["model_policy_source"] == "test_policy"


def test_runtime_fallback_has_separate_explanation_status():
    trust = build_ml_reference_trust(
        make_ml_research(source_type="runtime_fallback", freshness="missing"),
        model_policy={"status": "normal", "model_version": "baseline_v1"},
    )

    assert trust["status"] == "reduced_trust"
    assert trust["explanation"]["status"] == "fallback"
    assert "runtime_fallback" in trust["explanation"]["reason_codes"]


def test_unavailable_and_skipped_have_clear_usage_guidance():
    unavailable = build_ml_reference_trust(
        {"status": "unavailable", "reason": "missing_ml_artifacts"},
        model_policy={"status": "normal"},
    )
    skipped = build_ml_reference_trust(
        {
            "status": "skipped",
            "reason": "ml_disabled_for_internal_workflow",
            "source": {"type": "skipped"},
        },
        model_policy={"status": "normal"},
    )

    assert unavailable["status"] == "unavailable"
    assert "忽略 ML Reference" in unavailable["explanation"]["how_to_use"]
    assert skipped["status"] == "skipped"
    assert skipped["explanation"]["status"] == "skipped"
    assert "不需要解讀 ML 數字" in skipped["explanation"]["how_to_use"]


def test_single_stock_report_renders_concise_trust_explanation():
    ml_research = make_ml_research()
    ml_research["targets"]["up_20d"]["signal_quality"] = "low"
    trust = build_ml_reference_trust(
        ml_research,
        model_policy={
            "status": "reduced_trust",
            "model_version": "baseline_v1",
            "source": "test_policy",
            "calibration_findings": 4,
            "candidate_promoted": False,
        },
    )

    report = build_ml_reference(
        {
            "ml_research": ml_research,
            "ml_reference_trust": trust,
        }
    )

    assert "ML 信任說明:" in report
    assert "信任狀態：降低信任" in report
    assert "版本化模型政策記錄 4 項校準改善事項" in report
    assert "不可單獨改變結論、價格計畫或出場決策" in report


def test_theme_report_inserts_structured_trust_explanation():
    trust = build_ml_reference_trust(
        make_ml_research(),
        model_policy={
            "status": "reduced_trust",
            "model_version": "baseline_v1",
            "source": "test_policy",
            "calibration_findings": 4,
            "candidate_promoted": False,
        },
    )
    report = enforce_theme_ml_reference_trust(
        data={"theme_ml_reference_trust": trust},
        report="主題摘要\n\nML Reference\n- 20 日上漲機率 50%。\n\n風險提醒\n- test",
    )

    assert "ML 信任說明:" in report
    assert "信任狀態：降低信任" in report
    assert "版本化模型政策記錄 4 項校準改善事項" in report
