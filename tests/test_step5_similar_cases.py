from similar_cases import (
    MARKET_UNIVERSE_PLAN,
    RELAXATION_STEPS,
    SIMILAR_CASE_SCHEMA,
    SimilarCaseRecord,
    build_similar_case_result_rows,
    build_similar_case_query,
    classify_news_event_type,
    classify_peer_market_evidence_quality,
    classify_technical_pattern,
    find_similar_cases,
)


def make_case(
    ticker,
    *,
    themes=("memory",),
    industry="semiconductor",
    technical_pattern="breakout",
    news_event_type="industry_demand",
    market_regime="bull",
    return_20d=0.05,
):
    return SimilarCaseRecord(
        ticker=ticker,
        event_date="2025-01-01",
        themes=themes,
        industry=industry,
        technical_pattern=technical_pattern,
        news_event_type=news_event_type,
        market_regime=market_regime,
        forward_return_5d=0.01,
        forward_return_10d=0.02,
        forward_return_20d=return_20d,
    )


def test_market_universe_plan_requires_provider_and_keeps_themes_as_fallback():
    assert MARKET_UNIVERSE_PLAN["primary_source"] == "provider"
    assert MARKET_UNIVERSE_PLAN["first_version_universe"] == "QQQ100 / QQQ holdings"
    assert MARKET_UNIVERSE_PLAN["local_reference"] == "data/themes.py"
    assert MARKET_UNIVERSE_PLAN["provider_required"] is True
    assert "tickers" in SIMILAR_CASE_SCHEMA
    assert "similar_case_results" in SIMILAR_CASE_SCHEMA


def test_build_similar_case_query_uses_local_theme_classification():
    query = build_similar_case_query(
        ticker="MU",
        technical_pattern="breakout",
        news_event_type="industry_demand",
        market_regime="bull",
    )

    assert query.ticker == "MU"
    assert "memory" in query.themes
    assert "semiconductor" in query.themes


def test_find_similar_cases_uses_exact_peer_context_first():
    query = build_similar_case_query(
        ticker="MU",
        technical_pattern="breakout",
        news_event_type="industry_demand",
        market_regime="bull",
    )
    records = [
        make_case("WDC"),
        make_case("STX"),
        make_case("SNDK"),
        make_case("NVDA"),
        make_case("AMD"),
        make_case("MU"),
    ]

    result = find_similar_cases(query=query, records=records, min_samples=5)

    assert result["status"] == "success"
    assert result["scope"] == "peer_group"
    assert result["relaxation_step"] == "exact_peer_context"
    assert result["similarity"] == "high"
    assert result["summary"]["sample_size"] == 5
    assert result["summary"]["win_rate_20d"] == 1.0
    assert result["summary"]["evidence_quality"] == "low_to_medium"


def test_find_similar_cases_relaxes_to_market_wide_when_peer_samples_are_too_few():
    query = build_similar_case_query(
        ticker="MU",
        technical_pattern="breakout",
        news_event_type="industry_demand",
        market_regime="bull",
    )
    records = [
        make_case("WDC"),
        make_case("STX"),
        make_case(
            "AAPL",
            themes=("mega_cap_tech",),
            industry="hardware",
            news_event_type="product",
        ),
        make_case(
            "MSFT",
            themes=("software_cloud",),
            industry="software",
            news_event_type="product",
        ),
        make_case(
            "META",
            themes=("internet_platforms",),
            industry="internet",
            news_event_type="analyst_rating",
        ),
    ]

    result = find_similar_cases(query=query, records=records, min_samples=5)

    assert result["status"] == "success"
    assert result["scope"] == "market_wide"
    assert result["relaxation_step"] == "technical_regime_market"
    assert result["similarity"] == "low_to_medium"
    assert result["summary"]["sample_size"] == 5
    assert result["summary"]["evidence_quality"] == "low_to_medium"


def test_peer_market_evidence_quality_caps_relaxed_large_samples_at_medium():
    assert (
        classify_peer_market_evidence_quality(sample_size=50, similarity="high")
        == "high"
    )
    assert (
        classify_peer_market_evidence_quality(
            sample_size=120,
            similarity="low_to_medium",
        )
        == "medium"
    )
    assert (
        classify_peer_market_evidence_quality(sample_size=20, similarity="high")
        == "medium"
    )
    assert (
        classify_peer_market_evidence_quality(sample_size=5, similarity="high")
        == "low_to_medium"
    )
    assert classify_peer_market_evidence_quality(sample_size=4, similarity="high") == "low"
    assert classify_peer_market_evidence_quality(sample_size=0, similarity="high") == "none"


def test_relaxation_steps_document_expected_order():
    assert [step["name"] for step in RELAXATION_STEPS] == [
        "exact_peer_context",
        "without_news_event",
        "technical_regime_market",
        "technical_only_market",
    ]


def test_classifies_dataset_rows_for_similar_case_accumulation():
    row = {
        "is_breakout": False,
        "is_volume_surge": False,
        "is_pullback": False,
        "price_vs_ma20": -0.03,
        "macd_histogram": -1.2,
        "risk_event_count_30d": 0,
        "earnings_guidance_count_30d": 2,
        "product_demand_count_30d": 0,
        "news_missing": False,
    }

    assert classify_technical_pattern(row) == "below_ma20_negative_momentum"
    assert classify_news_event_type(row) == "earnings_guidance"


def test_build_similar_case_result_rows_from_training_dataset(tmp_path):
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,date,is_breakout,is_volume_surge,is_pullback,price_vs_ma20,macd_histogram,market_regime,risk_event_count_30d,earnings_guidance_count_30d,product_demand_count_30d,news_missing,forward_return_5d,forward_return_10d,forward_return_20d",
                "WDC,2026-01-01,true,false,false,0.05,1.0,bull,0,1,0,false,0.01,0.02,0.05",
                "STX,2026-01-02,true,false,false,0.04,1.1,bull,0,1,0,false,0.01,0.02,0.04",
                "SNDK,2026-01-03,true,false,false,0.03,1.2,bull,0,1,0,false,0.01,0.02,0.03",
                "NVDA,2026-01-04,true,false,false,0.02,1.3,bull,0,1,0,false,0.01,0.02,0.02",
                "AMD,2026-01-05,true,false,false,0.01,1.4,bull,0,1,0,false,0.01,0.02,0.01",
                "MU,2026-01-06,true,false,false,0.06,1.5,bull,0,1,0,false,0.01,0.02,0.06",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_similar_case_result_rows(
        dataset_path=csv_path,
        ticker_metadata=[
            {"ticker": "MU", "industry": "semiconductor", "themes": ["memory"]},
            {"ticker": "WDC", "industry": "semiconductor", "themes": ["memory"]},
            {"ticker": "STX", "industry": "semiconductor", "themes": ["memory"]},
            {"ticker": "SNDK", "industry": "semiconductor", "themes": ["memory"]},
            {"ticker": "NVDA", "industry": "semiconductor", "themes": ["semiconductor"]},
            {"ticker": "AMD", "industry": "semiconductor", "themes": ["semiconductor"]},
        ],
        latest_per_ticker=True,
        min_samples=5,
    )

    row = next(item for item in result["result_rows"] if item["query_ticker"] == "MU")

    assert result["result_count"] == 6
    assert row["technical_pattern"] == "breakout"
    assert row["sample_size"] >= 5
    assert row["evidence_quality"] in {"low_to_medium", "medium", "high"}
