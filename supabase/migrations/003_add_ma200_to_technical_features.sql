-- Step 6.6: add MA200 for benchmark market-regime support.

alter table if exists public.technical_features
    add column if not exists ma200 numeric;
