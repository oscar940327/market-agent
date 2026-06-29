-- Step 6.5: add short moving averages for technical feature storage.

alter table if exists public.technical_features
    add column if not exists ma5 numeric,
    add column if not exists ma10 numeric;
