-- Step 6.8J: record optional news LLM escalation metadata.

alter table public.news_events
    add column if not exists escalation_enabled boolean not null default false,
    add column if not exists escalated boolean not null default false,
    add column if not exists escalation_model text,
    add column if not exists escalation_reason text,
    add column if not exists escalation_status text not null default 'not_applicable',
    add column if not exists escalation_error text;

alter table public.news_events
    drop constraint if exists news_events_escalation_status_value;

alter table public.news_events
    add constraint news_events_escalation_status_value check (
        escalation_status in (
            'not_applicable',
            'not_needed',
            'success',
            'failed'
        )
    );

create index if not exists idx_news_events_escalation_status
    on public.news_events (escalation_status, fetched_at);

create index if not exists idx_news_events_escalated
    on public.news_events (escalated, fetched_at);
