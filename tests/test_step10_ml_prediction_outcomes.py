import json
import subprocess

from data_store.supabase_store import (
    fetch_ml_predictions_for_outcomes,
    upsert_ml_prediction_outcomes,
)
from ml_prediction_outcomes import build_single_ml_prediction_outcomes
from scripts import compute_ml_prediction_outcomes as script


def make_prediction():
    return {
        "id": "prediction-1",
        "ticker": "MU",
        "prediction_date": "2026-06-30",
        "price_provider": "yfinance",
        "up_probability_5d": 0.6,
        "up_probability_10d": 0.4,
        "up_probability_20d": 0.55,
        "large_drop_risk_20d": 0.7,
        "predicted_return_5d": 0.02,
        "predicted_return_10d": -0.01,
        "predicted_return_20d": 0.05,
        "feature_snapshot": {"close": 100.0},
    }


def make_price_rows(length=25):
    return [
        {
            "date": f"2026-06-{30 + index:02d}" if index == 0 else f"2026-07-{index:02d}",
            "close": 100 + index,
        }
        for index in range(length)
    ]


def test_build_single_ml_prediction_outcomes_computes_5_10_20_trading_days():
    updates = build_single_ml_prediction_outcomes(
        prediction=make_prediction(),
        price_data=make_price_rows(),
    )

    by_horizon = {row["horizon_trading_days"]: row for row in updates}

    assert set(by_horizon) == {5, 10, 20}
    assert by_horizon[5]["outcome_status"] == "computed"
    assert by_horizon[5]["actual_return_pct"] == 0.05
    assert by_horizon[5]["actual_up"] is True
    assert by_horizon[5]["up_prediction_correct"] is True
    assert by_horizon[10]["up_prediction_correct"] is False
    assert by_horizon[20]["large_drop_prediction_correct"] is False
    assert by_horizon[20]["return_error"] == 0.15


def test_build_single_ml_prediction_outcomes_keeps_unmatured_horizon_pending():
    updates = build_single_ml_prediction_outcomes(
        prediction=make_prediction(),
        price_data=make_price_rows(length=8),
    )

    by_horizon = {row["horizon_trading_days"]: row for row in updates}

    assert by_horizon[5]["outcome_status"] == "computed"
    assert by_horizon[10]["outcome_status"] == "pending"
    assert by_horizon[20]["outcome_status"] == "pending"


def test_build_single_ml_prediction_outcomes_marks_missing_prediction_price():
    prediction = make_prediction()
    prediction["prediction_date"] = "2026-06-29"

    updates = build_single_ml_prediction_outcomes(
        prediction=prediction,
        price_data=make_price_rows(),
    )

    assert {row["outcome_status"] for row in updates} == {"missing_price"}


def test_fetch_ml_predictions_for_outcomes_queries_ready_predictions():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'[{"id":"prediction-1","ticker":"MU"}]'

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    rows = fetch_ml_predictions_for_outcomes(
        universe="QQQ100",
        limit=25,
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert rows == [{"id": "prediction-1", "ticker": "MU"}]
    assert "ml_predictions?select=" in captured["url"]
    assert "ml_prediction_outcomes" in captured["url"]
    assert "prediction_status=eq.ready" in captured["url"]
    assert "limit=25" in captured["url"]


def test_upsert_ml_prediction_outcomes_uses_prediction_horizon_conflict_key():
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

    result = upsert_ml_prediction_outcomes(
        [
            {
                "ml_prediction_id": "prediction-1",
                "ticker": "MU",
                "prediction_date": "2026-06-30",
                "horizon_trading_days": 5,
                "outcome_status": "computed",
            }
        ],
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result == {"status": "success", "upserted_count": 1}
    assert "on_conflict=ml_prediction_id,horizon_trading_days" in captured["url"]
    assert captured["payload"][0]["ticker"] == "MU"


def test_compute_ml_prediction_outcomes_script_groups_prices_and_writes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(script, "fetch_ml_predictions_for_outcomes", lambda universe, limit: [make_prediction()])
    monkeypatch.setattr(script, "fetch_daily_prices", lambda ticker, provider: make_price_rows())

    captured = {}

    def fake_upsert(updates):
        captured["updates"] = updates
        return {"status": "success", "upserted_count": len(updates)}

    monkeypatch.setattr(script, "upsert_ml_prediction_outcomes", fake_upsert)

    result = script.main(["--output-dir", str(tmp_path)])

    output = capsys.readouterr().out
    assert result == 0
    assert "predictions=1" in output
    assert "computed=3" in output
    assert "predictions_to_update=1" in output
    assert "json_path=" in output
    assert "supabase=success" in output
    assert len(captured["updates"]) == 3


def test_compute_ml_prediction_outcomes_skips_completed_predictions(monkeypatch, tmp_path, capsys):
    prediction = make_prediction()
    prediction["ml_prediction_outcomes"] = [
        {"horizon_trading_days": 5, "outcome_status": "computed"},
        {"horizon_trading_days": 10, "outcome_status": "computed"},
        {"horizon_trading_days": 20, "outcome_status": "computed"},
    ]
    monkeypatch.setattr(
        script,
        "fetch_ml_predictions_for_outcomes",
        lambda universe, limit: [prediction],
    )
    monkeypatch.setattr(script, "fetch_daily_prices", lambda ticker, provider: [])

    captured = {}

    def fake_upsert(updates):
        captured["updates"] = updates
        return {"status": "skipped", "upserted_count": 0}

    monkeypatch.setattr(script, "upsert_ml_prediction_outcomes", fake_upsert)

    result = script.main(["--skip-supabase", "--output-dir", str(tmp_path)])

    output = capsys.readouterr().out
    assert result == 0
    assert "predictions=1" in output
    assert "predictions_skipped_completed=1" in output
    assert "predictions_to_update=0" in output
    assert "updates=0" in output
