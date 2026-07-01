-- Step 9.1: store daily ML prediction runs, predictions, and matured outcomes.

create table if not exists public.ml_model_runs (
    id uuid primary key default gen_random_uuid(),
    run_name text,
    run_type text not null default 'daily_prediction',
    model_type text not null,
    model_version text not null,
    feature_version text not null,
    dataset_version text,
    training_data_start date,
    training_data_end date,
    universe text not null default 'QQQ100',
    provider text not null default 'yfinance',
    data_as_of date not null,
    pipeline_run_id text,
    model_artifact_path text,
    metrics jsonb not null default '{}'::jsonb,
    config jsonb not null default '{}'::jsonb,
    notes text,
    status text not null default 'completed',
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    constraint ml_model_runs_run_type_value check (
        run_type in (
            'training',
            'daily_prediction',
            'backfill_prediction',
            'experiment',
            'manual'
        )
    ),
    constraint ml_model_runs_model_type_value check (
        model_type in (
            'classification',
            'return_regression',
            'historical_reference',
            'hybrid',
            'experiment'
        )
    ),
    constraint ml_model_runs_status_value check (
        status in ('running', 'completed', 'failed', 'partial_success')
    ),
    constraint ml_model_runs_data_range_order check (
        training_data_start is null
        or training_data_end is null
        or training_data_start <= training_data_end
    )
);

create index if not exists idx_ml_model_runs_version_as_of
    on public.ml_model_runs (model_version, feature_version, data_as_of);

create index if not exists idx_ml_model_runs_type_status_created
    on public.ml_model_runs (run_type, status, created_at);

create index if not exists idx_ml_model_runs_pipeline
    on public.ml_model_runs (pipeline_run_id)
    where pipeline_run_id is not null;

create table if not exists public.ml_predictions (
    id uuid primary key default gen_random_uuid(),
    model_run_id uuid not null references public.ml_model_runs(id) on delete cascade,
    ticker text not null,
    prediction_date date not null,
    data_as_of date not null,
    universe text not null default 'QQQ100',
    price_provider text not null default 'yfinance',
    model_version text not null,
    feature_version text not null,
    prediction_status text not null default 'ready',
    prediction_freshness text not null default 'fresh',
    up_probability_5d numeric,
    up_probability_10d numeric,
    up_probability_20d numeric,
    large_drop_risk_20d numeric,
    historical_sample_size integer,
    historical_evidence_quality text,
    historical_avg_return_5d numeric,
    historical_avg_return_10d numeric,
    historical_avg_return_20d numeric,
    historical_return_5d_p25 numeric,
    historical_return_5d_p75 numeric,
    historical_return_10d_p25 numeric,
    historical_return_10d_p75 numeric,
    historical_return_20d_p25 numeric,
    historical_return_20d_p75 numeric,
    historical_max_drop_20d_p25 numeric,
    historical_max_drop_20d_p75 numeric,
    predicted_return_5d numeric,
    predicted_return_10d numeric,
    predicted_return_20d numeric,
    predicted_max_drop_20d numeric,
    predicted_return_5d_p25 numeric,
    predicted_return_5d_p75 numeric,
    predicted_return_10d_p25 numeric,
    predicted_return_10d_p75 numeric,
    predicted_return_20d_p25 numeric,
    predicted_return_20d_p75 numeric,
    predicted_max_drop_20d_p25 numeric,
    predicted_max_drop_20d_p75 numeric,
    model_quality text,
    evidence_quality text,
    signal_clarity text,
    data_completeness text,
    news_coverage text,
    fundamental_coverage text,
    prediction_payload jsonb not null default '{}'::jsonb,
    feature_snapshot jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ml_predictions_ticker_uppercase check (ticker = upper(ticker)),
    constraint ml_predictions_probability_range check (
        (up_probability_5d is null or (up_probability_5d >= 0 and up_probability_5d <= 1))
        and (up_probability_10d is null or (up_probability_10d >= 0 and up_probability_10d <= 1))
        and (up_probability_20d is null or (up_probability_20d >= 0 and up_probability_20d <= 1))
        and (large_drop_risk_20d is null or (large_drop_risk_20d >= 0 and large_drop_risk_20d <= 1))
    ),
    constraint ml_predictions_nonnegative_sample check (
        historical_sample_size is null or historical_sample_size >= 0
    ),
    constraint ml_predictions_status_value check (
        prediction_status in ('ready', 'partial', 'stale', 'failed', 'unavailable')
    ),
    constraint ml_predictions_freshness_value check (
        prediction_freshness in ('fresh', 'warning', 'stale', 'missing', 'unknown')
    ),
    constraint ml_predictions_quality_values check (
        (model_quality is null or model_quality in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (evidence_quality is null or evidence_quality in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (historical_evidence_quality is null or historical_evidence_quality in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (signal_clarity is null or signal_clarity in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (data_completeness is null or data_completeness in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (news_coverage is null or news_coverage in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
        and (fundamental_coverage is null or fundamental_coverage in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        ))
    ),
    constraint ml_predictions_unique_key unique (
        ticker,
        prediction_date,
        model_version,
        feature_version,
        universe
    )
);

create index if not exists idx_ml_predictions_ticker_date
    on public.ml_predictions (ticker, prediction_date);

create index if not exists idx_ml_predictions_latest
    on public.ml_predictions (ticker, data_as_of, prediction_freshness);

create index if not exists idx_ml_predictions_model_run
    on public.ml_predictions (model_run_id);

create index if not exists idx_ml_predictions_quality
    on public.ml_predictions (model_quality, evidence_quality);

create table if not exists public.ml_prediction_outcomes (
    id uuid primary key default gen_random_uuid(),
    ml_prediction_id uuid not null references public.ml_predictions(id) on delete cascade,
    ticker text not null,
    prediction_date date not null,
    horizon_trading_days integer not null,
    target_date date,
    actual_date date,
    price_at_prediction numeric,
    price_at_horizon numeric,
    actual_return_pct numeric,
    actual_up boolean,
    actual_max_drop_pct numeric,
    actual_max_runup_pct numeric,
    predicted_up_probability numeric,
    predicted_return numeric,
    predicted_large_drop_risk numeric,
    up_prediction_correct boolean,
    large_drop_prediction_correct boolean,
    return_error numeric,
    outcome_status text not null default 'pending',
    price_provider text not null default 'yfinance',
    computed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ml_prediction_outcomes_ticker_uppercase check (ticker = upper(ticker)),
    constraint ml_prediction_outcomes_horizon_value check (
        horizon_trading_days in (5, 10, 20)
    ),
    constraint ml_prediction_outcomes_status_value check (
        outcome_status in ('pending', 'ready', 'missing_price', 'computed', 'skipped')
    ),
    constraint ml_prediction_outcomes_probability_range check (
        (predicted_up_probability is null or (predicted_up_probability >= 0 and predicted_up_probability <= 1))
        and (predicted_large_drop_risk is null or (predicted_large_drop_risk >= 0 and predicted_large_drop_risk <= 1))
    ),
    constraint ml_prediction_outcomes_unique_key unique (
        ml_prediction_id,
        horizon_trading_days
    )
);

create index if not exists idx_ml_prediction_outcomes_ticker_prediction_date
    on public.ml_prediction_outcomes (ticker, prediction_date);

create index if not exists idx_ml_prediction_outcomes_status_target
    on public.ml_prediction_outcomes (outcome_status, target_date);

create index if not exists idx_ml_prediction_outcomes_horizon_computed
    on public.ml_prediction_outcomes (horizon_trading_days, computed_at);
