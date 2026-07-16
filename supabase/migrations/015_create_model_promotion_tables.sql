-- Step 30: monthly candidate review and shadow validation lifecycle.

alter table public.ml_predictions
    add column if not exists prediction_role text not null default 'production';

alter table public.ml_predictions
    drop constraint if exists ml_predictions_prediction_role_value;

alter table public.ml_predictions
    add constraint ml_predictions_prediction_role_value check (
        prediction_role in ('production', 'shadow')
    );

create index if not exists idx_ml_predictions_role_model_date
    on public.ml_predictions (prediction_role, model_version, prediction_date desc);

create table if not exists public.ml_model_registry (
    id uuid primary key default gen_random_uuid(),
    model_version text not null unique,
    model_role text not null,
    lifecycle_status text not null,
    source_report_version text,
    dataset_version text,
    feature_version text,
    data_as_of date,
    started_at timestamptz,
    completed_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ml_model_registry_role_value check (
        model_role in ('production', 'candidate', 'shadow')
    ),
    constraint ml_model_registry_status_value check (
        lifecycle_status in (
            'registered',
            'shadow_active',
            'shadow_observing',
            'promotion_recommended',
            'rejected',
            'retired'
        )
    )
);

create index if not exists idx_ml_model_registry_role_status
    on public.ml_model_registry (model_role, lifecycle_status, created_at desc);

create table if not exists public.ml_promotion_reviews (
    id uuid primary key default gen_random_uuid(),
    review_version text not null,
    review_month date not null,
    production_model_version text not null,
    candidate_model_version text,
    recommendation text not null,
    recommendation_label text not null,
    shadow_outcome_count integer not null default 0,
    report jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint ml_promotion_reviews_recommendation_value check (
        recommendation in (
            'no_candidate',
            'keep_production',
            'start_shadow',
            'continue_shadow',
            'promote_candidate',
            'unable_to_decide'
        )
    ),
    constraint ml_promotion_reviews_shadow_count_nonnegative check (
        shadow_outcome_count >= 0
    ),
    constraint ml_promotion_reviews_unique_month_candidate unique (
        review_month,
        production_model_version,
        candidate_model_version
    )
);

create index if not exists idx_ml_promotion_reviews_month
    on public.ml_promotion_reviews (review_month desc, created_at desc);

