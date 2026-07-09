-- Step 21: track Research Report / Research Signal outcomes.

alter table public.research_logs
    add column if not exists workflow_kind text,
    add column if not exists conclusion text,
    add column if not exists valuation_label text,
    add column if not exists technical_label text,
    add column if not exists news_sentiment text,
    add column if not exists ml_reference_status text,
    add column if not exists ml_reference_trust_status text,
    add column if not exists data_freshness_status text,
    add column if not exists exit_signal text,
    add column if not exists research_signal_score numeric,
    add column if not exists price_plan jsonb not null default '{}',
    add column if not exists tracking_status text not null default 'not_configured',
    add column if not exists tracked_tickers text[] not null default '{}',
    add column if not exists tracking_notes text;

alter table public.research_outcomes
    add column if not exists intent text,
    add column if not exists theme text,
    add column if not exists conclusion text,
    add column if not exists exit_signal text,
    add column if not exists entry_touched boolean,
    add column if not exists exit_touched boolean,
    add column if not exists stop_loss_touched boolean,
    add column if not exists price_plan jsonb not null default '{}',
    add column if not exists tracking_notes text;

alter table public.research_outcomes
    drop constraint if exists research_outcomes_status_value;

alter table public.research_outcomes
    add constraint research_outcomes_status_value check (
        outcome_status in ('pending', 'ready', 'missing_price', 'computed', 'skipped')
    );

alter table public.research_outcomes
    drop constraint if exists research_outcomes_unique_key;

alter table public.research_outcomes
    add constraint research_outcomes_unique_key unique (
        research_log_id,
        ticker,
        horizon_trading_days
    );

create index if not exists idx_research_logs_tracking_status_created
    on public.research_logs (tracking_status, created_at);

create index if not exists idx_research_outcomes_intent_status
    on public.research_outcomes (intent, outcome_status);
