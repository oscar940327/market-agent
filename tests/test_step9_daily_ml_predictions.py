import json
from urllib.error import HTTPError

from daily_ml_predictions import (
    build_failed_prediction_record,
    build_ml_model_run_row,
    build_prediction_record,
    build_snapshot_states,
)
from data_store.supabase_store import (
    insert_ml_model_run,
    upsert_ml_predictions,
)
from scripts import build_daily_ml_predictions as script
from ml_versions import build_versioning_payload


def make_ml_research():
    return {
        "status": "success",
        "model_version": "baseline_v1",
        "feature_version": "ml_features_v1",
        "targets": {
            "up_5d": {"probability": 0.43, "signal_quality": "low"},
            "up_10d": {"probability": 0.48, "signal_quality": "low_to_medium"},
            "up_20d": {"probability": 0.61, "signal_quality": "medium"},
            "large_drop_20d": {"probability": 0.32, "signal_quality": "low"},
        },
        "return_reference": {
            "sample_size": 80,
            "evidence_quality": "high",
            "historical_average_return_5d": 0.01,
            "historical_average_return_10d": 0.02,
            "historical_average_return_20d": 0.03,
            "expected_return_range_5d": {"low": -0.02, "high": 0.04},
            "expected_return_range_10d": {"low": -0.03, "high": 0.06},
            "expected_return_range_20d": {"low": -0.05, "high": 0.10},
            "max_drop_range_20d": {"low": -0.12, "high": -0.03},
        },
        "return_model": {
            "status": "success",
            "targets": {
                "forward_return_5d": {
                    "predicted_value": 0.018,
                    "predicted_range": {"low": -0.01, "high": 0.05},
                    "model_quality": "low_to_medium",
                },
                "forward_return_10d": {
                    "predicted_value": 0.028,
                    "predicted_range": {"low": -0.02, "high": 0.07},
                    "model_quality": "low_to_medium",
                },
                "forward_return_20d": {
                    "predicted_value": 0.044,
                    "predicted_range": {"low": -0.04, "high": 0.11},
                    "model_quality": "low",
                },
                "max_drop_20d": {
                    "predicted_value": -0.08,
                    "predicted_range": {"low": -0.13, "high": -0.04},
                    "model_quality": "low_to_medium",
                },
            },
        },
    }


def make_feature_row():
    return {
        "ticker": "MU",
        "date": "2026-06-30",
        "data_as_of": "2026-06-30",
        "feature_version": "ml_features_v1",
        "price_vs_ma20": 0.08,
        "rsi_14": 59.0,
        "macd": 91.1,
        "macd_histogram": -2.1,
        "is_breakout": False,
        "is_volume_surge": False,
        "is_pullback": False,
        "market_regime": "bull",
        "news_count_30d": 5,
        "news_sentiment_score_30d": 0.4,
        "risk_event_count_30d": 0,
        "news_missing": False,
    }


def test_build_prediction_record_maps_ml_reference_to_supabase_row():
    record = build_prediction_record(
        ticker="MU",
        model_run_id="11111111-1111-1111-1111-111111111111",
        ml_research=make_ml_research(),
        feature_row=make_feature_row(),
        ticker_metadata={
            "ticker": "MU",
            "industry": "semiconductor",
            "themes": ["memory", "ai"],
        },
        data_freshness={"overall": "fresh"},
    )

    assert record["ticker"] == "MU"
    assert record["prediction_date"] == "2026-06-30"
    assert record["prediction_status"] == "ready"
    assert record["prediction_freshness"] == "fresh"
    assert record["up_probability_20d"] == 0.61
    assert record["large_drop_risk_20d"] == 0.32
    assert record["historical_sample_size"] == 80
    assert record["historical_return_20d_p25"] == -0.05
    assert record["predicted_return_20d"] == 0.044
    assert record["predicted_max_drop_20d_p25"] == -0.13
    assert record["model_quality"] == "low"
    assert record["evidence_quality"] == "high"
    assert record["feature_snapshot"]["industry"] == "semiconductor"
    assert record["prediction_payload"]["market_snapshot"]["ml_state"] == "bullish"
    assert record["prediction_payload"]["versioning"] == build_versioning_payload()
    json.dumps(record, allow_nan=False)


def test_build_snapshot_states_includes_broader_market_fields():
    states = build_snapshot_states(
        feature_row=make_feature_row(),
        ml_research=make_ml_research(),
        ticker_metadata={"industry": "semiconductor", "themes": ["memory"]},
        data_freshness={"overall": "warning"},
    )

    assert states["industry"] == "semiconductor"
    assert states["themes"] == ["memory"]
    assert states["market_regime"] == "bull"
    assert states["technical_state"] == "neutral"
    assert states["news_state"] == "positive"
    assert states["ml_state"] == "bullish"
    assert states["risk_state"] == "medium"
    assert states["data_freshness"] == "warning"
    assert states["candidate_reason"]


def test_failed_prediction_record_keeps_pipeline_moving():
    record = build_failed_prediction_record(
        ticker="MU",
        model_run_id="11111111-1111-1111-1111-111111111111",
        error_message="boom",
        data_as_of="2026-06-30",
    )

    assert record["prediction_status"] == "failed"
    assert record["prediction_payload"]["error"] == "boom"
    assert record["data_completeness"] == "low"
    json.dumps(record, allow_nan=False)


def test_build_records_for_tickers_retries_then_records_failed_prediction(monkeypatch):
    calls = {"count": 0}

    def always_fail(**kwargs):
        calls["count"] += 1
        raise RuntimeError("temporary failure")

    monkeypatch.setattr(script, "build_record_for_ticker", always_fail)

    records, failures = script.build_records_for_tickers(
        tickers=["MU"],
        ticker_metadata={"MU": {"ticker": "MU"}},
        model_run_id="11111111-1111-1111-1111-111111111111",
        universe="QQQ100",
        provider="yfinance",
        retry_per_ticker=1,
        dataset_path="dataset.csv",
        model_dir="models",
        metrics_path="metrics.json",
        return_model_dir="return_models",
        return_metrics_path="return_metrics.json",
        metadata_path="metadata.json",
        skip_freshness=True,
    )

    assert calls["count"] == 2
    assert len(records) == 1
    assert records[0]["prediction_status"] == "failed"
    assert failures == [
        {"ticker": "MU", "attempts": 2, "error": "temporary failure"}
    ]


def test_build_ml_model_run_row_is_json_safe():
    row = build_ml_model_run_row(
        data_as_of="2026-06-30",
        pipeline_run_id="pipeline-1",
        config={"tickers": ["MU"]},
    )

    assert row["run_type"] == "daily_prediction"
    assert row["model_type"] == "hybrid"
    assert row["model_version"] == "daily_prediction_v1"
    assert row["data_as_of"] == "2026-06-30"
    assert row["pipeline_run_id"] == "pipeline-1"
    assert row["config"]["versioning"] == build_versioning_payload()
    json.dumps(row, allow_nan=False)


def test_insert_ml_model_run_posts_to_supabase(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'[{"id":"run-1"}]'

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    result = insert_ml_model_run(
        {"model_version": "v1", "data_as_of": "2026-06-30"},
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result == {"status": "success", "row": {"id": "run-1"}}
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/rest/v1/ml_model_runs")
    assert captured["payload"]["model_version"] == "v1"


def test_upsert_ml_predictions_uses_unique_conflict_key():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b""

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    result = upsert_ml_predictions(
        [
            {
                "ticker": "MU",
                "prediction_date": "2026-06-30",
                "model_version": "baseline_v1",
                "feature_version": "ml_features_v1",
                "universe": "QQQ100",
            }
        ],
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result == {"status": "success", "upserted_count": 1}
    assert "on_conflict=ticker,prediction_date,model_version,feature_version,universe" in captured["url"]
    assert captured["payload"][0]["ticker"] == "MU"
