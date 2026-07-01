from pathlib import Path


MIGRATION_PATH = Path("supabase/migrations/008_create_ml_prediction_tables.sql")


def read_migration() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_step9_migration_creates_prediction_tables():
    sql = read_migration()

    assert "create table if not exists public.ml_model_runs" in sql
    assert "create table if not exists public.ml_predictions" in sql
    assert "create table if not exists public.ml_prediction_outcomes" in sql


def test_ml_model_runs_tracks_model_and_data_versions():
    sql = read_migration()

    for column in [
        "run_type text not null default 'daily_prediction'",
        "model_type text not null",
        "model_version text not null",
        "feature_version text not null",
        "dataset_version text",
        "training_data_start date",
        "training_data_end date",
        "data_as_of date not null",
        "pipeline_run_id text",
        "metrics jsonb not null default '{}'::jsonb",
        "config jsonb not null default '{}'::jsonb",
    ]:
        assert column in sql

    assert "ml_model_runs_run_type_value" in sql
    assert "ml_model_runs_model_type_value" in sql
    assert "ml_model_runs_status_value" in sql


def test_ml_predictions_stores_daily_reference_outputs():
    sql = read_migration()

    for column in [
        "model_run_id uuid not null references public.ml_model_runs(id) on delete cascade",
        "ticker text not null",
        "prediction_date date not null",
        "data_as_of date not null",
        "up_probability_5d numeric",
        "up_probability_10d numeric",
        "up_probability_20d numeric",
        "large_drop_risk_20d numeric",
        "historical_sample_size integer",
        "historical_evidence_quality text",
        "historical_avg_return_5d numeric",
        "historical_return_20d_p25 numeric",
        "predicted_return_20d numeric",
        "predicted_max_drop_20d numeric",
        "model_quality text",
        "evidence_quality text",
        "prediction_payload jsonb not null default '{}'::jsonb",
        "feature_snapshot jsonb not null default '{}'::jsonb",
    ]:
        assert column in sql

    assert "ml_predictions_probability_range" in sql
    assert "ml_predictions_quality_values" in sql
    assert "ml_predictions_unique_key unique" in sql
    assert "ticker,\n        prediction_date,\n        model_version,\n        feature_version,\n        universe" in sql


def test_ml_prediction_outcomes_keeps_model_monitoring_separate_from_research_outcomes():
    sql = read_migration()

    for column in [
        "ml_prediction_id uuid not null references public.ml_predictions(id) on delete cascade",
        "horizon_trading_days integer not null",
        "actual_return_pct numeric",
        "actual_up boolean",
        "actual_max_drop_pct numeric",
        "predicted_up_probability numeric",
        "predicted_large_drop_risk numeric",
        "up_prediction_correct boolean",
        "large_drop_prediction_correct boolean",
        "return_error numeric",
        "outcome_status text not null default 'pending'",
    ]:
        assert column in sql

    assert "ml_prediction_outcomes_horizon_value" in sql
    assert "horizon_trading_days in (5, 10, 20)" in sql
    assert "ml_prediction_outcomes_unique_key unique" in sql
