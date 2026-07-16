import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from model_promotion import (
    build_monthly_promotion_review,
    build_shadow_prediction_records,
    train_shadow_candidate_models,
)
from scripts import run_monthly_model_promotion as script


GENERATED = datetime(2026, 7, 17, tzinfo=UTC)


def test_rejected_step28_candidate_keeps_production():
    report = build_monthly_promotion_review(
        step28_report={"promotion": {"status": "do_not_promote"}},
        production_model_version="baseline_v1",
        generated_at=GENERATED,
    )

    assert report["recommendation"] == "keep_production"
    assert report["recommendation_label"] == "不建議更換正式模型"
    assert report["automatic_replacement"] is False
    assert report["research_report_affected"] is False


def test_ready_candidate_starts_shadow_without_replacing_production():
    report = build_monthly_promotion_review(
        step28_report={"promotion": {"status": "candidate_bundle_ready"}},
        production_model_version="baseline_v1",
        generated_at=GENERATED,
    )

    assert report["recommendation"] == "start_shadow"
    assert report["candidate_model_version"] == "candidate_202607"
    assert report["shadow_visibility"] == "monitoring_only"


def test_active_shadow_waits_for_mature_outcomes():
    active = {
        "model_version": "candidate_202605",
        "started_at": (GENERATED - timedelta(days=70)).isoformat(),
    }
    report = build_monthly_promotion_review(
        step28_report=None,
        production_model_version="baseline_v1",
        active_shadow=active,
        shadow_outcomes=make_outcomes(30, correct=True),
        generated_at=GENERATED,
    )

    assert report["recommendation"] == "continue_shadow"
    assert report["recommendation_label"] == "建議繼續並行觀察"


def test_mature_better_shadow_produces_explicit_promotion_recommendation():
    active = {
        "model_version": "candidate_202604",
        "started_at": (GENERATED - timedelta(days=90)).isoformat(),
    }
    production = make_outcomes(120, correct=False, probability=0.55)
    shadow = make_outcomes(120, correct=True, probability=0.80)

    report = build_monthly_promotion_review(
        step28_report=None,
        production_model_version="baseline_v1",
        active_shadow=active,
        production_outcomes=production,
        shadow_outcomes=shadow,
        generated_at=GENERATED,
    )

    assert report["recommendation"] == "promote_candidate"
    assert report["recommendation_label"] == "建議更換正式模型"
    assert report["requires_user_confirmation"] is True
    assert report["automatic_replacement"] is False


def test_shadow_models_create_hidden_prediction_records():
    dataset = make_dataset()
    step28 = {
        "promotion": {
            "status": "candidate_bundle_ready",
            "passed_targets": ["up_5d"],
        },
        "targets": {
            "up_5d": {
                "target_type": "classification",
                "best_candidate": "logistic_regression",
                "promotion_decision": "pass",
            }
        },
    }
    bundle = train_shadow_candidate_models(
        dataset,
        step28_report=step28,
        candidate_version="candidate_202607",
        max_train_rows=500,
    )
    records = build_shadow_prediction_records(
        dataset,
        candidate_bundle=bundle,
        model_run_id="00000000-0000-0000-0000-000000000000",
    )

    assert bundle["status"] == "success"
    assert len(records) == 2
    assert all(record["prediction_role"] == "shadow" for record in records)
    assert all(record["prediction_payload"]["research_report_visible"] is False for record in records)
    assert all(record["up_probability_5d"] is not None for record in records)


def test_monthly_script_writes_clear_dry_run_email_report(tmp_path, capsys):
    step28_path = tmp_path / "step28.json"
    step28_path.write_text(
        json.dumps({"promotion": {"status": "do_not_promote"}}),
        encoding="utf-8",
    )

    exit_code = script.main(
        [
            "--step28-path",
            str(step28_path),
            "--output-dir",
            str(tmp_path),
            "--dry-run",
            "--send-email",
            "--dry-run-email",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "recommendation=keep_production" in output
    assert "recommendation_label=不建議更換正式模型" in output
    assert "email=dry_run" in output
    assert list(tmp_path.glob("model_promotion_review_*.json"))


def make_outcomes(count_per_horizon, *, correct, probability=0.8):
    rows = []
    for horizon in (5, 10, 20):
        for index in range(count_per_horizon):
            actual_up = index % 2 == 0
            predicted_probability = probability if actual_up == correct else 1 - probability
            actual_drop = -0.10 if index % 4 == 0 else -0.02
            rows.append(
                {
                    "horizon_trading_days": horizon,
                    "outcome_status": "computed",
                    "actual_up": actual_up,
                    "predicted_up_probability": predicted_probability,
                    "up_prediction_correct": correct,
                    "actual_max_drop_pct": actual_drop,
                    "predicted_large_drop_risk": 0.9 if actual_drop <= -0.08 else 0.1,
                }
            )
    return rows


def make_dataset():
    rows = []
    for index, row_date in enumerate(pd.date_range("2024-01-01", periods=80, freq="D")):
        for ticker_number, ticker in enumerate(("MU", "NVDA")):
            positive = (index + ticker_number) % 2 == 0
            rows.append(
                {
                    "ticker": ticker,
                    "date": row_date.date().isoformat(),
                    "price_vs_ma20": 0.04 if positive else -0.04,
                    "price_vs_ma50": 0.03 if positive else -0.03,
                    "price_vs_ma200": 0.02 if positive else -0.02,
                    "rsi_14": 60 if positive else 40,
                    "macd_histogram": 0.2 if positive else -0.2,
                    "volatility_20d": 0.02 if positive else 0.05,
                    "volume_ratio_20d": 1.2,
                    "market_regime": "bull" if positive else "bear",
                    "volatility_regime": "normal" if positive else "high",
                    "up_5d": positive,
                }
            )
    return pd.DataFrame(rows)

