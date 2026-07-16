create table if not exists public.ml_dataset_metadata (
  id uuid primary key default gen_random_uuid(),
  dataset_name text not null default 'training_dataset_v1',
  dataset_version text not null default 'training_dataset_v1',
  universe text not null default 'QQQ100',
  provider text not null default 'yfinance',
  feature_version text not null,
  label_version text not null,
  generated_at timestamptz not null,
  data_start_date date,
  data_end_date date,
  row_count integer not null default 0,
  status text not null default 'success',
  workflow_run_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (dataset_name, universe, provider),
  constraint ml_dataset_metadata_status_value check (
    status in ('success', 'partial_success', 'failed')
  ),
  constraint ml_dataset_metadata_row_count_nonnegative check (row_count >= 0)
);

create index if not exists ml_dataset_metadata_generated_idx
  on public.ml_dataset_metadata (generated_at desc);
