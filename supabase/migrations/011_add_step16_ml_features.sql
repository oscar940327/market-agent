alter table public.technical_features
    add column if not exists drawdown_from_20d_high numeric,
    add column if not exists drawdown_from_60d_high numeric,
    add column if not exists ma20_slope_5d numeric,
    add column if not exists ma50_slope_10d numeric,
    add column if not exists rsi_change_5d numeric,
    add column if not exists macd_histogram_change_5d numeric,
    add column if not exists days_above_ma20 integer,
    add column if not exists days_below_ma20 integer,
    add column if not exists volume_trend_20d numeric,
    add column if not exists volatility_regime text;
