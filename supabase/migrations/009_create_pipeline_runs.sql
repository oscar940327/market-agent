create table if not exists public.pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  pipeline text not null,
  status text not null,
  started_at timestamptz not null,
  finished_at timestamptz not null,
  duration_seconds numeric,
  options jsonb not null default '{}'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  steps jsonb not null default '[]'::jsonb,
  log_path text,
  latest_log_path text,
  created_at timestamptz not null default now()
);

create index if not exists pipeline_runs_pipeline_finished_idx
  on public.pipeline_runs (pipeline, finished_at desc);

create index if not exists pipeline_runs_pipeline_status_finished_idx
  on public.pipeline_runs (pipeline, status, finished_at desc);
