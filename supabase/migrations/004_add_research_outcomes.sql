-- Step 6.7: store post-research outcome tracking for 5/10/20 trading days.

create table if not exists public.research_outcomes (
    id uuid primary key default gen_random_uuid(),
    research_log_id uuid not null references public.research_logs(id) on delete cascade,
    ticker text not null,
    query_date date not null,
    horizon_trading_days integer not null,
    target_date date,
    actual_date date,
    price_at_query numeric,
    price_at_horizon numeric,
    return_pct numeric,
    max_drawdown_pct numeric,
    max_runup_pct numeric,
    outcome_status text not null default 'pending',
    price_provider text not null default 'yfinance',
    used_for_calibration boolean not null default false,
    calibration_notes text,
    computed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint research_outcomes_ticker_uppercase check (ticker = upper(ticker)),
    constraint research_outcomes_horizon_value check (
        horizon_trading_days in (5, 10, 20)
    ),
    constraint research_outcomes_status_value check (
        outcome_status in ('pending', 'ready', 'missing_price', 'computed')
    ),
    constraint research_outcomes_unique_key unique (
        research_log_id,
        horizon_trading_days
    )
);

create index if not exists idx_research_outcomes_ticker_query_date
    on public.research_outcomes (ticker, query_date);

create index if not exists idx_research_outcomes_status_target
    on public.research_outcomes (outcome_status, target_date);

create index if not exists idx_research_outcomes_calibration
    on public.research_outcomes (used_for_calibration, horizon_trading_days);
