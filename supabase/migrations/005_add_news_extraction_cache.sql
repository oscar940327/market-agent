-- Step 6.8I: cache news extraction metadata on news_events.

alter table public.news_events
    add column if not exists extractor_mode text,
    add column if not exists extractor_provider text,
    add column if not exists extractor_model text,
    add column if not exists extracted_at timestamptz,
    add column if not exists extraction_status text not null default 'unclassified',
    add column if not exists llm_summary text,
    add column if not exists ticker_relevance text,
    add column if not exists extraction_error text;

alter table public.news_events
    drop constraint if exists news_events_extraction_status_value;

alter table public.news_events
    add constraint news_events_extraction_status_value check (
        extraction_status in (
            'unclassified',
            'success',
            'fallback_rule_based',
            'error',
            'skipped_duplicate'
        )
    );

alter table public.news_events
    drop constraint if exists news_events_extractor_mode_value;

alter table public.news_events
    add constraint news_events_extractor_mode_value check (
        extractor_mode is null
        or extractor_mode in ('rule_based', 'llm')
    );

alter table public.news_events
    drop constraint if exists news_events_ticker_relevance_value;

alter table public.news_events
    add constraint news_events_ticker_relevance_value check (
        ticker_relevance is null
        or ticker_relevance in ('high', 'medium', 'low', 'unknown')
    );

create index if not exists idx_news_events_extraction_status
    on public.news_events (extraction_status, fetched_at);

create index if not exists idx_news_events_extractor_mode
    on public.news_events (extractor_mode, extracted_at);
