import json

import agent.market_manager as market_manager_module
from agent.analyst import format_single_stock_analysis
from daily_ml_predictions import (
    convert_saved_prediction_to_ml_research,
    is_saved_prediction_usable,
)
from data_store.supabase_store import fetch_latest_ml_prediction
from tests.test_step6_news_events import make_single_stock_report_data


def make_saved_prediction(**overrides):
    prediction = {
        "id": "prediction-1",
        "model_run_id": "run-1",
        "ticker": "MU",
        "prediction_date": "2026-07-01",
        "data_as_of": "2026-07-01",
        "prediction_status": "ready",
        "prediction_freshness": "fresh",
        "model_version": "baseline_v1",
        "feature_version": "ml_features_v1",
        "up_probability_5d": 0.43,
        "up_probability_10d": 0.48,
        "up_probability_20d": 0.61,
        "large_drop_risk_20d": 0.32,
        "prediction_payload": {
            "ml_research": {
                "status": "success",
                "usage_policy": "reference_only",
                "model_version": "baseline_v1",
                "feature_version": "ml_features_v1",
                "targets": {
                    "up_5d": {
                        "probability": 0.43,
                        "probability_percent": 43.0,
                        "signal_label": "slightly bearish",
                        "signal_quality": "low",
                    },
                    "up_10d": {
                        "probability": 0.48,
                        "probability_percent": 48.0,
                        "signal_label": "unclear direction",
                        "signal_quality": "low_to_medium",
                    },
                    "up_20d": {
                        "probability": 0.61,
                        "probability_percent": 61.0,
                        "signal_label": "bullish tilt",
                        "signal_quality": "medium",
                    },
                    "large_drop_20d": {
                        "probability": 0.32,
                        "probability_percent": 32.0,
                        "signal_label": "medium large-drop risk",
                        "signal_quality": "low",
                    },
                },
                "return_reference": {
                    "method": "historical_quantile_reference",
                    "sample_size": 80,
                    "evidence_quality": "high",
                },
            }
        },
    }
    prediction.update(overrides)
    return prediction


def test_saved_prediction_fresh_or_warning_is_usable():
    assert is_saved_prediction_usable(make_saved_prediction())
    assert is_saved_prediction_usable(
        make_saved_prediction(prediction_freshness="warning")
    )
    assert not is_saved_prediction_usable(
        make_saved_prediction(prediction_freshness="stale")
    )
    assert not is_saved_prediction_usable(
        make_saved_prediction(prediction_status="failed")
    )


def test_convert_saved_prediction_to_ml_research_preserves_payload_and_source():
    ml_research = convert_saved_prediction_to_ml_research(make_saved_prediction())

    assert ml_research["status"] == "success"
    assert ml_research["targets"]["up_20d"]["probability_percent"] == 61.0
    assert ml_research["source"] == {
        "type": "saved_daily_prediction",
        "data_as_of": "2026-07-01",
        "prediction_date": "2026-07-01",
        "prediction_freshness": "fresh",
        "prediction_status": "ready",
        "model_version": "baseline_v1",
        "feature_version": "ml_features_v1",
        "model_run_id": "run-1",
    }


def test_manager_uses_saved_prediction_before_runtime_fallback(monkeypatch):
    saved_prediction = make_saved_prediction()
    monkeypatch.setattr(
        market_manager_module,
        "safe_fetch_latest_ml_prediction",
        lambda ticker: saved_prediction,
    )

    def runtime_should_not_run(ticker):
        raise AssertionError("runtime ML fallback should not run")

    monkeypatch.setattr(
        market_manager_module,
        "build_single_stock_ml_research",
        runtime_should_not_run,
    )

    ml_research, ml_prediction = market_manager_module.build_ml_research_for_single_stock(
        ticker="MU",
        include_ml=True,
    )

    assert ml_prediction == saved_prediction
    assert ml_research["source"]["type"] == "saved_daily_prediction"
    assert ml_research["targets"]["up_20d"]["probability_percent"] == 61.0


def test_manager_falls_back_when_saved_prediction_is_stale(monkeypatch):
    stale_prediction = make_saved_prediction(prediction_freshness="stale")
    monkeypatch.setattr(
        market_manager_module,
        "safe_fetch_latest_ml_prediction",
        lambda ticker: stale_prediction,
    )
    monkeypatch.setattr(
        market_manager_module,
        "build_single_stock_ml_research",
        lambda ticker: {"status": "success", "targets": {}},
    )

    ml_research, ml_prediction = market_manager_module.build_ml_research_for_single_stock(
        ticker="MU",
        include_ml=True,
    )

    assert ml_prediction == stale_prediction
    assert ml_research["source"]["type"] == "runtime_fallback"
    assert ml_research["source"]["reason"] == "saved_prediction_not_usable:ready/stale"


def test_report_displays_saved_prediction_source():
    data = make_single_stock_report_data(news_events_summary=None)
    data["ml_research"] = convert_saved_prediction_to_ml_research(make_saved_prediction())

    report = format_single_stock_analysis(data)

    assert "ML source: saved daily prediction" in report
    assert "data as of 2026-07-01" in report
    assert "freshness fresh" in report


def test_fetch_latest_ml_prediction_queries_latest_row():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps([make_saved_prediction()]).encode("utf-8")

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    row = fetch_latest_ml_prediction(
        ticker="MU",
        universe="QQQ100",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert row["ticker"] == "MU"
    assert "ml_predictions?select=*" in captured["url"]
    assert "ticker=eq.MU" in captured["url"]
    assert "universe=eq.QQQ100" in captured["url"]
    assert "order=data_as_of.desc,created_at.desc" in captured["url"]
