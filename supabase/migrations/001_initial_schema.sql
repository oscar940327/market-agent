-- Market Agent initial Supabase schema.
-- Step 6.2 applies this SQL in Supabase. Do not store secrets in this file.

create extension if not exists pgcrypto;

create table if not exists public.tickers (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    name text,
    industry text,
    themes text[] not null default '{}',
    market_cap_bucket text,
    volatility_bucket text,
    universe text not null,
    universe_provider text not null,
    is_active boolean not null default true,
    first_seen_at timestamptz,
    last_seen_at timestamptz,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint tickers_ticker_uppercase check (ticker = upper(ticker)),
    constraint tickers_unique_ticker_universe unique (ticker, universe)
);

create index if not exists idx_tickers_ticker
    on public.tickers (ticker);

create index if not exists idx_tickers_universe_active
    on public.tickers (universe, is_active);

create index if not exists idx_tickers_themes
    on public.tickers using gin (themes);

create table if not exists public.daily_prices (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    date date not null,
    open numeric not null,
    high numeric not null,
    low numeric not null,
    close numeric not null,
    adj_close numeric,
    volume numeric not null,
    provider text not null,
    fetched_at timestamptz not null default now(),
    source_revision text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint daily_prices_ticker_uppercase check (ticker = upper(ticker)),
    constraint daily_prices_positive_prices check (
        open >= 0 and high >= 0 and low >= 0 and close >= 0
    ),
    constraint daily_prices_nonnegative_volume check (volume >= 0),
    constraint daily_prices_unique_ticker_date_provider unique (ticker, date, provider)
);

create index if not exists idx_daily_prices_ticker_date
    on public.daily_prices (ticker, date);

create index if not exists idx_daily_prices_provider_fetched
    on public.daily_prices (provider, fetched_at);

create table if not exists public.technical_features (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    date date not null,
    price_provider text not null,
    close numeric not null,
    volume numeric not null,
    ma5 numeric,
    ma10 numeric,
    ma20 numeric,
    ma50 numeric,
    ma200 numeric,
    rsi_14 numeric,
    macd numeric,
    macd_signal numeric,
    macd_histogram numeric,
    drawdown_from_20d_high numeric,
    drawdown_from_60d_high numeric,
    ma20_slope_5d numeric,
    ma50_slope_10d numeric,
    rsi_change_5d numeric,
    macd_histogram_change_5d numeric,
    days_above_ma20 integer,
    days_below_ma20 integer,
    volume_trend_20d numeric,
    volatility_regime text,
    short_term_trend text,
    momentum_state text,
    is_breakout boolean not null default false,
    is_volume_surge boolean not null default false,
    is_pullback boolean not null default false,
    feature_version text not null default 'v1',
    computed_at timestamptz not null default now(),
    constraint technical_features_ticker_uppercase check (ticker = upper(ticker)),
    constraint technical_features_nonnegative_price_volume check (
        close >= 0 and volume >= 0
    ),
    constraint technical_features_rsi_range check (
        rsi_14 is null or (rsi_14 >= 0 and rsi_14 <= 100)
    ),
    constraint technical_features_trend_value check (
        short_term_trend is null
        or short_term_trend in ('strong', 'neutral', 'weak', 'unknown')
    ),
    constraint technical_features_unique_key unique (
        ticker,
        date,
        price_provider,
        feature_version
    )
);

create index if not exists idx_technical_features_ticker_date
    on public.technical_features (ticker, date);

create index if not exists idx_technical_features_breakout_date
    on public.technical_features (is_breakout, date);

create index if not exists idx_technical_features_volume_surge_date
    on public.technical_features (is_volume_surge, date);

create index if not exists idx_technical_features_pullback_date
    on public.technical_features (is_pullback, date);

create index if not exists idx_technical_features_momentum_date
    on public.technical_features (momentum_state, date);

create table if not exists public.market_regimes (
    id uuid primary key default gen_random_uuid(),
    date date not null,
    benchmark text not null,
    regime text not null,
    close numeric,
    ma200 numeric,
    three_month_return numeric,
    regime_changed boolean not null default false,
    previous_regime text,
    rule_version text not null default 'v1',
    data_as_of date not null,
    checked_at timestamptz not null default now(),
    constraint market_regimes_benchmark_uppercase check (benchmark = upper(benchmark)),
    constraint market_regimes_regime_value check (
        regime in ('bull', 'bear', 'sideways', 'unknown')
    ),
    constraint market_regimes_previous_regime_value check (
        previous_regime is null
        or previous_regime in ('bull', 'bear', 'sideways', 'unknown')
    ),
    constraint market_regimes_unique_key unique (date, benchmark, rule_version)
);

create index if not exists idx_market_regimes_benchmark_date
    on public.market_regimes (benchmark, date);

create index if not exists idx_market_regimes_regime_date
    on public.market_regimes (regime, date);

create index if not exists idx_market_regimes_changed_checked
    on public.market_regimes (regime_changed, checked_at);

create table if not exists public.news_events (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    source text not null,
    source_type text not null,
    title text not null,
    content_snippet text,
    url text,
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    sentiment text not null default 'unknown',
    topic text not null default 'general',
    importance text not null default 'unknown',
    source_quality text not null default 'unknown',
    duplicate_group_id text,
    ticker_mapping_confidence text,
    created_at timestamptz not null default now(),
    constraint news_events_ticker_uppercase check (ticker = upper(ticker)),
    constraint news_events_sentiment_value check (
        sentiment in ('positive', 'negative', 'neutral', 'unknown')
    ),
    constraint news_events_importance_value check (
        importance in ('high', 'medium', 'low', 'unknown')
    ),
    constraint news_events_source_quality_value check (
        source_quality in ('high', 'medium', 'low', 'unknown')
    ),
    constraint news_events_ticker_mapping_confidence_value check (
        ticker_mapping_confidence is null
        or ticker_mapping_confidence in ('high', 'medium', 'low', 'unknown')
    )
);

create unique index if not exists idx_news_events_unique_url
    on public.news_events (url)
    where url is not null;

create index if not exists idx_news_events_ticker_published
    on public.news_events (ticker, published_at);

create index if not exists idx_news_events_duplicate_group
    on public.news_events (duplicate_group_id);

create index if not exists idx_news_events_topic_published
    on public.news_events (topic, published_at);

create index if not exists idx_news_events_importance_published
    on public.news_events (importance, published_at);

create table if not exists public.social_events (
    id uuid primary key default gen_random_uuid(),
    ticker text not null,
    source text not null,
    source_type text not null default 'social',
    post_id text,
    author_id_hash text,
    content_snippet text,
    url text,
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    sentiment text not null default 'unknown',
    topic text,
    engagement_count integer,
    discussion_volume integer,
    source_quality text not null default 'unknown',
    spam_risk text not null default 'unknown',
    duplicate_group_id text,
    created_at timestamptz not null default now(),
    constraint social_events_ticker_uppercase check (ticker = upper(ticker)),
    constraint social_events_sentiment_value check (
        sentiment in ('positive', 'negative', 'neutral', 'unknown')
    ),
    constraint social_events_source_quality_value check (
        source_quality in ('high', 'medium', 'low', 'unknown')
    ),
    constraint social_events_spam_risk_value check (
        spam_risk in ('high', 'medium', 'low', 'unknown')
    ),
    constraint social_events_nonnegative_counts check (
        (engagement_count is null or engagement_count >= 0)
        and (discussion_volume is null or discussion_volume >= 0)
    )
);

create unique index if not exists idx_social_events_unique_source_post
    on public.social_events (source, post_id)
    where post_id is not null;

create index if not exists idx_social_events_ticker_published
    on public.social_events (ticker, published_at);

create index if not exists idx_social_events_source_fetched
    on public.social_events (source, fetched_at);

create index if not exists idx_social_events_spam_risk_published
    on public.social_events (spam_risk, published_at);

create table if not exists public.research_logs (
    id uuid primary key default gen_random_uuid(),
    query text not null,
    intent text not null,
    ticker text,
    theme text,
    workflow_kind text,
    decision text,
    conclusion text,
    valuation_label text,
    technical_label text,
    news_sentiment text,
    ml_reference_status text,
    ml_reference_trust_status text,
    data_freshness_status text,
    exit_signal text,
    research_signal_score numeric,
    evidence_quality text,
    price_at_query numeric,
    data_as_of date,
    report_summary text,
    request_options jsonb,
    output_snapshot jsonb,
    price_plan jsonb not null default '{}',
    tracking_status text not null default 'not_configured',
    tracked_tickers text[] not null default '{}',
    tracking_notes text,
    created_at timestamptz not null default now(),
    constraint research_logs_ticker_uppercase check (
        ticker is null or ticker = upper(ticker)
    ),
    constraint research_logs_evidence_quality_value check (
        evidence_quality is null
        or evidence_quality in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        )
    )
);

create index if not exists idx_research_logs_ticker_created
    on public.research_logs (ticker, created_at);

create index if not exists idx_research_logs_intent_created
    on public.research_logs (intent, created_at);

create index if not exists idx_research_logs_evidence_created
    on public.research_logs (evidence_quality, created_at);

create index if not exists idx_research_logs_tracking_status_created
    on public.research_logs (tracking_status, created_at);

create table if not exists public.similar_case_results (
    id uuid primary key default gen_random_uuid(),
    query_ticker text not null,
    query_date date not null,
    scope text not null,
    relaxation_step text not null,
    matched_fields text[] not null default '{}',
    technical_pattern text not null,
    news_event_type text,
    market_regime text,
    sample_size integer not null default 0,
    win_rate_5d numeric,
    win_rate_10d numeric,
    win_rate_20d numeric,
    average_forward_return_20d numeric,
    max_loss_20d numeric,
    evidence_quality text not null,
    source_data_as_of date not null,
    result_status text not null default 'fresh',
    created_at timestamptz not null default now(),
    refreshed_at timestamptz,
    constraint similar_case_results_query_ticker_uppercase check (
        query_ticker = upper(query_ticker)
    ),
    constraint similar_case_results_scope_value check (
        scope in ('peer_group', 'market_wide', 'none')
    ),
    constraint similar_case_results_nonnegative_sample check (sample_size >= 0),
    constraint similar_case_results_win_rates_range check (
        (win_rate_5d is null or (win_rate_5d >= 0 and win_rate_5d <= 1))
        and (win_rate_10d is null or (win_rate_10d >= 0 and win_rate_10d <= 1))
        and (win_rate_20d is null or (win_rate_20d >= 0 and win_rate_20d <= 1))
    ),
    constraint similar_case_results_evidence_quality_value check (
        evidence_quality in (
            'high',
            'medium',
            'low_to_medium',
            'low',
            'none',
            'not_used',
            'not_applicable',
            'skipped',
            'unknown'
        )
    ),
    constraint similar_case_results_result_status_value check (
        result_status in ('fresh', 'stale', 'missing', 'planned')
    ),
    constraint similar_case_results_market_regime_value check (
        market_regime is null
        or market_regime in ('bull', 'bear', 'sideways', 'unknown')
    ),
    constraint similar_case_results_unique_query unique (
        query_ticker,
        query_date
    )
);

create index if not exists idx_similar_case_results_query_date
    on public.similar_case_results (query_ticker, query_date);

create index if not exists idx_similar_case_results_scope_step
    on public.similar_case_results (scope, relaxation_step);

create index if not exists idx_similar_case_results_pattern_regime
    on public.similar_case_results (technical_pattern, market_regime);

create index if not exists idx_similar_case_results_status_as_of
    on public.similar_case_results (result_status, source_data_as_of);
