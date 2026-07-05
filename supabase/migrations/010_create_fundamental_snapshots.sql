create table if not exists public.fundamental_snapshots (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  as_of_date date not null,
  provider text not null default 'yfinance',
  status text not null default 'success',
  market_cap numeric,
  trailing_pe numeric,
  forward_pe numeric,
  price_to_sales numeric,
  revenue_growth numeric,
  earnings_growth numeric,
  gross_margins numeric,
  operating_margins numeric,
  profit_margins numeric,
  free_cashflow numeric,
  debt_to_equity numeric,
  earnings_date text,
  sector text,
  industry text,
  summary jsonb not null default '{}'::jsonb,
  raw_metrics jsonb not null default '{}'::jsonb,
  source_error text,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ticker, as_of_date, provider)
);

create index if not exists fundamental_snapshots_ticker_as_of_idx
  on public.fundamental_snapshots (ticker, as_of_date desc, fetched_at desc);

create index if not exists fundamental_snapshots_status_idx
  on public.fundamental_snapshots (status);
