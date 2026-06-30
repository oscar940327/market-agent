-- Step 8.2: store daily news summaries for pipeline checks and report payloads.

create table if not exists public.news_event_summaries (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    summary_date date not null,
    window_days integer not null,
    total_items integer not null default 0,
    overall_sentiment text not null default 'unknown',
    dominant_topic text not null default 'general',
    dominant_topic_label text,
    high_importance_count integer not null default 0,
    summary_json jsonb not null default '{}'::jsonb,
    provider text not null default 'market_agent',
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint news_event_summaries_ticker_uppercase check (ticker = upper(ticker)),
    constraint news_event_summaries_positive_window check (window_days > 0),
    constraint news_event_summaries_nonnegative_counts check (
        total_items >= 0 and high_importance_count >= 0
    ),
    constraint news_event_summaries_sentiment_value check (
        overall_sentiment in ('positive', 'negative', 'neutral', 'unknown')
    ),
    constraint news_event_summaries_unique_key unique (
        ticker,
        summary_date,
        window_days,
        provider
    )
);

create index if not exists idx_news_event_summaries_ticker_date
    on public.news_event_summaries (ticker, summary_date desc);

create index if not exists idx_news_event_summaries_generated
    on public.news_event_summaries (generated_at desc);
