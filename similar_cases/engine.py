from data.themes import THEMES
from similar_cases.schema import SimilarCaseQuery, SimilarCaseRecord


RELAXATION_STEPS = [
    {
        "name": "exact_peer_context",
        "scope": "peer_group",
        "similarity": "high",
        "fields": [
            "industry_or_theme",
            "technical_pattern",
            "news_event_type",
            "market_regime",
        ],
    },
    {
        "name": "without_news_event",
        "scope": "peer_group",
        "similarity": "medium",
        "fields": [
            "industry_or_theme",
            "technical_pattern",
            "market_regime",
        ],
    },
    {
        "name": "technical_regime_market",
        "scope": "market_wide",
        "similarity": "low_to_medium",
        "fields": [
            "technical_pattern",
            "market_regime",
        ],
    },
    {
        "name": "technical_only_market",
        "scope": "market_wide",
        "similarity": "low",
        "fields": [
            "technical_pattern",
        ],
    },
]


def build_similar_case_query(
    *,
    ticker: str,
    technical_pattern: str,
    market_regime: str,
    news_event_type: str | None = None,
    industry: str | None = None,
    market_cap_bucket: str | None = None,
    volatility_bucket: str | None = None,
    universe: str = "QQQ100",
) -> SimilarCaseQuery:
    return SimilarCaseQuery(
        ticker=ticker.upper(),
        technical_pattern=technical_pattern,
        market_regime=market_regime,
        themes=tuple(get_ticker_theme_keys(ticker)),
        industry=industry,
        market_cap_bucket=market_cap_bucket,
        volatility_bucket=volatility_bucket,
        news_event_type=news_event_type,
        universe=universe,
    )


def get_ticker_theme_keys(ticker: str) -> list[str]:
    normalized_ticker = ticker.upper()
    themes = []

    for theme_key, theme in THEMES.items():
        if normalized_ticker in theme["tickers"]:
            themes.append(theme_key)

    return themes


def find_similar_cases(
    *,
    query: SimilarCaseQuery,
    records: list[SimilarCaseRecord],
    min_samples: int = 5,
) -> dict:
    for step in RELAXATION_STEPS:
        matched_records = [
            record
            for record in records
            if record.ticker.upper() != query.ticker.upper()
            and record.universe == query.universe
            and matches_relaxation_step(query=query, record=record, step=step)
        ]

        if len(matched_records) >= min_samples:
            return {
                "status": "success",
                "scope": step["scope"],
                "relaxation_step": step["name"],
                "similarity": step["similarity"],
                "matched_fields": step["fields"],
                "cases": matched_records,
                "summary": summarize_similar_cases(
                    cases=matched_records,
                    similarity=step["similarity"],
                ),
            }

    return {
        "status": "no_data",
        "scope": "none",
        "relaxation_step": "no_matching_cases",
        "similarity": "none",
        "matched_fields": [],
        "cases": [],
        "summary": summarize_similar_cases(cases=[], similarity="none"),
    }


def matches_relaxation_step(
    *,
    query: SimilarCaseQuery,
    record: SimilarCaseRecord,
    step: dict,
) -> bool:
    fields = set(step["fields"])

    if "industry_or_theme" in fields and not matches_industry_or_theme(query, record):
        return False

    if (
        "technical_pattern" in fields
        and record.technical_pattern != query.technical_pattern
    ):
        return False

    if "news_event_type" in fields and query.news_event_type:
        if record.news_event_type != query.news_event_type:
            return False

    if "market_regime" in fields and record.market_regime != query.market_regime:
        return False

    return True


def matches_industry_or_theme(
    query: SimilarCaseQuery,
    record: SimilarCaseRecord,
) -> bool:
    if query.industry and record.industry == query.industry:
        return True

    return bool(set(query.themes).intersection(record.themes))


def summarize_similar_cases(
    *,
    cases: list[SimilarCaseRecord],
    similarity: str,
) -> dict:
    sample_size = len(cases)
    return_5d = compact_returns(cases, "forward_return_5d")
    return_10d = compact_returns(cases, "forward_return_10d")
    return_20d = compact_returns(cases, "forward_return_20d")
    evidence_quality = classify_peer_market_evidence_quality(
        sample_size=sample_size,
        similarity=similarity,
    )

    return {
        "sample_size": sample_size,
        "win_rate_5d": calculate_win_rate(return_5d),
        "win_rate_10d": calculate_win_rate(return_10d),
        "win_rate_20d": calculate_win_rate(return_20d),
        "average_forward_return_20d": calculate_average(return_20d),
        "max_loss_20d": min(return_20d) if return_20d else None,
        "evidence_quality": evidence_quality,
        "reason": build_summary_reason(
            sample_size=sample_size,
            similarity=similarity,
            evidence_quality=evidence_quality,
        ),
    }


def compact_returns(cases: list[SimilarCaseRecord], field_name: str) -> list[float]:
    values = []

    for case in cases:
        value = getattr(case, field_name)
        if value is not None:
            values.append(float(value))

    return values


def calculate_win_rate(values: list[float]) -> float | None:
    if not values:
        return None

    wins = len([value for value in values if value > 0])
    return round(wins / len(values), 4)


def calculate_average(values: list[float]) -> float | None:
    if not values:
        return None

    return round(sum(values) / len(values), 4)


def classify_peer_market_evidence_quality(
    *,
    sample_size: int,
    similarity: str,
) -> str:
    if sample_size <= 0:
        return "none"

    if sample_size < 5:
        return "low"

    if sample_size < 20:
        return "low_to_medium"

    if sample_size < 50:
        return "medium"

    if similarity == "high":
        return "high"

    return "medium"


def build_summary_reason(
    *,
    sample_size: int,
    similarity: str,
    evidence_quality: str,
) -> str:
    if sample_size == 0:
        return "沒有找到可用的 peer group 或 market-wide 相似案例。"

    if evidence_quality == "high":
        return (
            f"找到 {sample_size} 筆高度相似案例，樣本數足夠，"
            "可作為 peer / market evidence 的高品質參考。"
        )

    if similarity != "high" and sample_size >= 50:
        return (
            f"找到 {sample_size} 筆案例，但條件已放寬，"
            "因此即使樣本數多也不給 high。"
        )

    return (
        f"找到 {sample_size} 筆相似案例，條件相似度為 {similarity}，"
        f"證據品質為 {evidence_quality}。"
    )
