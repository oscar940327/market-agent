from dataclasses import dataclass, field


MARKET_UNIVERSE_PLAN = {
    "first_version_universe": "QQQ100 / QQQ holdings",
    "primary_source": "provider",
    "local_reference": "data/themes.py",
    "local_reference_role": "theme classification, seed, and fallback only",
    "provider_required": True,
    "provider_unavailable_behavior": (
        "return an explicit provider limitation instead of pretending local themes "
        "are a complete QQQ100 source"
    ),
}


SIMILAR_CASE_SCHEMA = {
    "tickers": [
        "ticker",
        "name",
        "industry",
        "themes",
        "market_cap_bucket",
        "volatility_bucket",
        "universe",
        "universe_provider",
        "is_active",
        "updated_at",
    ],
    "technical_events": [
        "ticker",
        "event_date",
        "technical_pattern",
        "close",
        "volume",
        "rsi14",
        "macd_histogram",
        "market_regime",
        "forward_return_5d",
        "forward_return_10d",
        "forward_return_20d",
    ],
    "news_events": [
        "ticker",
        "event_date",
        "news_event_type",
        "sentiment",
        "importance",
        "source_quality",
        "duplicate_group_id",
    ],
    "similar_case_results": [
        "query_ticker",
        "query_date",
        "scope",
        "relaxation_step",
        "sample_size",
        "win_rate_5d",
        "win_rate_10d",
        "win_rate_20d",
        "average_forward_return_20d",
        "max_loss_20d",
        "evidence_quality",
        "created_at",
    ],
}


@dataclass(frozen=True)
class SimilarCaseQuery:
    ticker: str
    technical_pattern: str
    market_regime: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    industry: str | None = None
    market_cap_bucket: str | None = None
    volatility_bucket: str | None = None
    news_event_type: str | None = None
    universe: str = "QQQ100"


@dataclass(frozen=True)
class SimilarCaseRecord:
    ticker: str
    event_date: str
    technical_pattern: str
    market_regime: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    industry: str | None = None
    market_cap_bucket: str | None = None
    volatility_bucket: str | None = None
    news_event_type: str | None = None
    universe: str = "QQQ100"
    forward_return_5d: float | None = None
    forward_return_10d: float | None = None
    forward_return_20d: float | None = None
