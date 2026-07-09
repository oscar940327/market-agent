from ml_model_improvement import apply_downside_risk_overlay, build_downside_risk_overlay
from daily_ml_predictions import convert_saved_prediction_to_ml_research


def make_ml_research():
    return {
        "status": "success",
        "targets": {
            "large_drop_20d": {
                "probability": 0.55,
                "probability_percent": 55.0,
                "signal_label": "high large-drop risk",
                "signal_quality": "medium",
            }
        },
        "return_model": {
            "status": "success",
            "targets": {
                "max_drop_20d": {
                    "predicted_value": -0.04,
                    "predicted_percent": -4.0,
                    "predicted_range": {
                        "low": -0.06,
                        "high": -0.02,
                        "low_percent": -6.0,
                        "high_percent": -2.0,
                    },
                    "model_quality": "low_to_medium",
                }
            },
        },
    }


def make_high_risk_feature_snapshot():
    return {
        "price_vs_ma20": -0.05,
        "macd_histogram": -1.2,
        "volatility_20d": 0.05,
        "risk_event_count_30d": 1,
        "market_regime": "bear",
        "market_snapshot": {
            "technical_state": "bearish",
            "risk_state": "high",
        },
    }


def test_downside_overlay_builds_conservative_max_drop_reference():
    overlay = build_downside_risk_overlay(
        feature_snapshot=make_high_risk_feature_snapshot(),
        ml_research=make_ml_research(),
    )

    assert overlay["active"] is True
    assert overlay["risk_level"] == "severe"
    assert overlay["conservative_max_drop"] == -0.14
    assert "price_below_ma20" in overlay["reasons"]


def test_apply_downside_overlay_updates_max_drop_target_but_keeps_raw_value():
    output = apply_downside_risk_overlay(
        make_ml_research(),
        make_high_risk_feature_snapshot(),
    )

    target = output["return_model"]["targets"]["max_drop_20d"]

    assert output["downside_risk_overlay"]["active"] is True
    assert target["raw_predicted_value"] == -0.04
    assert target["predicted_value"] == -0.14
    assert target["predicted_range"]["low"] == -0.14
    assert target["overlay_applied"] is True


def test_downside_overlay_stays_inactive_for_low_risk_snapshot():
    output = apply_downside_risk_overlay(
        make_ml_research(),
        {
            "price_vs_ma20": 0.08,
            "macd_histogram": 0.4,
            "volatility_20d": 0.02,
            "market_regime": "bull",
            "market_snapshot": {
                "technical_state": "bullish",
                "risk_state": "low",
            },
        },
    )

    target = output["return_model"]["targets"]["max_drop_20d"]

    assert output["downside_risk_overlay"]["active"] is False
    assert target["predicted_value"] == -0.04
    assert "raw_predicted_value" not in target


def test_saved_prediction_conversion_applies_downside_overlay_from_feature_snapshot():
    ml_research = convert_saved_prediction_to_ml_research(
        {
            "model_run_id": "run-1",
            "prediction_date": "2026-07-01",
            "data_as_of": "2026-07-01",
            "prediction_status": "ready",
            "prediction_freshness": "fresh",
            "model_version": "baseline_v1",
            "feature_version": "ml_features_v1",
            "prediction_payload": {"ml_research": make_ml_research()},
            "feature_snapshot": make_high_risk_feature_snapshot(),
        }
    )

    assert ml_research["source"]["type"] == "saved_daily_prediction"
    assert ml_research["downside_risk_overlay"]["active"] is True
