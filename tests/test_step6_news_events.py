import json
from datetime import UTC, datetime

from data_store.supabase_store import insert_news_events
from data_store.supabase_store import fetch_news_events
from data_store.supabase_store import update_news_event_classification
from agent.experts.news_agent import run_news_agent
from agent.analyst import format_single_stock_analysis
from news_events.classification import classify_news_event
from news_events.extraction_cache import (
    build_duplicate_classification_update,
    build_extraction_update,
    find_cached_duplicate_classification,
    is_news_event_classified,
    should_escalate_news_event,
    should_skip_event,
)
from news_events.extractor import (
    OpenRouterNewsExtractorClient,
    classify_news_event_with_optional_llm,
    get_news_extractor_client_from_env,
)
from news_events.normalization import (
    build_duplicate_group_id,
    build_news_event_rows,
    classify_ticker_mapping_confidence,
    normalize_title,
)
from news_events.summary import build_news_summary
from news_events.providers import fetch_google_news_rss
from news_events.providers import parse_yfinance_datetime


SAMPLE_RSS = b"""
<rss>
  <channel>
    <item>
      <title>Micron shares rise on AI memory demand - Reuters</title>
      <link>https://example.com/mu-ai-memory</link>
      <pubDate>Fri, 26 Jun 2026 13:00:00 GMT</pubDate>
      <source>Reuters</source>
      <description>Micron is seeing stronger demand.</description>
    </item>
  </channel>
</rss>
"""


def test_fetch_google_news_rss_normalizes_provider_items():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return SAMPLE_RSS

    def fake_open_url(request, timeout):
        assert "news.google.com/rss/search" in request.full_url
        return FakeResponse()

    items = fetch_google_news_rss(
        ticker="MU",
        max_items=1,
        open_url=fake_open_url,
    )

    assert items == [
        {
            "provider": "google_news_rss",
            "source": "Reuters",
            "source_type": "news_aggregator",
            "title": "Micron shares rise on AI memory demand - Reuters",
            "content_snippet": "Micron is seeing stronger demand.",
            "url": "https://example.com/mu-ai-memory",
            "published_at": "2026-06-26T13:00:00+00:00",
        }
    ]


def test_build_news_event_rows_adds_dedup_and_mapping_metadata():
    rows = build_news_event_rows(
        ticker="MU",
        raw_items=[
            {
                "provider": "google_news_rss",
                "source": "Reuters",
                "source_type": "news_aggregator",
                "title": "Micron shares rise on AI memory demand - Reuters",
                "content_snippet": "Micron is seeing stronger demand.",
                "url": "https://example.com/mu-ai-memory",
                "published_at": "2026-06-26T13:00:00+00:00",
            }
        ],
    )

    row = rows[0]

    assert row["ticker"] == "MU"
    assert row["source_quality"] == "high"
    assert row["ticker_mapping_confidence"] == "high"
    assert row["duplicate_group_id"]
    assert row["sentiment"] == "positive"
    assert row["topic"] == "product_demand"
    assert row["importance"] == "medium"
    assert row["extractor_mode"] == "rule_based"
    assert row["extraction_status"] == "success"


def test_duplicate_group_id_ignores_trailing_source_name():
    first = build_duplicate_group_id(
        ticker="MU",
        title="Micron shares rise on AI memory demand - Reuters",
        published_at="2026-06-26T13:00:00+00:00",
    )
    second = build_duplicate_group_id(
        ticker="MU",
        title="Micron shares rise on AI memory demand - Yahoo Finance",
        published_at="2026-06-26T15:00:00+00:00",
    )

    assert first == second
    assert normalize_title("Micron shares rise - Reuters") == "micron shares rise"


def test_ticker_mapping_confidence_can_mark_weak_theme_news():
    confidence = classify_ticker_mapping_confidence(
        ticker="MU",
        title="Chip stocks rise as AI demand grows",
        snippet="Semiconductor names moved higher.",
        provider=None,
    )

    assert confidence == "low"


def test_insert_news_events_ignores_duplicate_url_conflicts():
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return b""

    def fake_open_url(request, timeout):
        calls.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    result = insert_news_events(
        [
            {
                "ticker": "MU",
                "source": "Reuters",
                "source_type": "news_aggregator",
                "title": "Micron news",
                "url": "https://example.com/mu",
                "sentiment": "unknown",
                "topic": "general",
                "importance": "unknown",
                "source_quality": "high",
                "duplicate_group_id": "abc",
            }
        ],
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result["status"] == "success"
    assert result["inserted_count"] == 1
    assert calls[0]["ticker"] == "MU"


def test_update_news_event_classification_sends_extractor_metadata():
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return b""

    def fake_open_url(request, timeout):
        calls.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    result = update_news_event_classification(
        event_id="event-1",
        sentiment="positive",
        topic="earnings_guidance",
        importance="high",
        ticker_relevance="high",
        llm_summary="這是一則財報相關新聞。",
        extractor_mode="llm",
        extractor_provider="openrouter",
        extractor_model="openai/gpt-5.4-mini",
        extracted_at="2026-06-28T00:00:00+00:00",
        extraction_status="success",
        escalation_enabled=True,
        escalated=True,
        escalation_model="openai/gpt-5.5",
        escalation_reason="risk_event",
        escalation_status="success",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result["status"] == "success"
    assert calls[0]["extractor_mode"] == "llm"
    assert calls[0]["extractor_provider"] == "openrouter"
    assert calls[0]["llm_summary"] == "這是一則財報相關新聞。"
    assert calls[0]["ticker_relevance"] == "high"
    assert calls[0]["escalated"] is True
    assert calls[0]["escalation_model"] == "openai/gpt-5.5"


def test_parse_yfinance_datetime_accepts_iso_timestamp():
    assert parse_yfinance_datetime("2026-06-25T23:13:47Z") == "2026-06-25T23:13:47+00:00"


def test_classify_news_event_maps_topic_sentiment_and_importance():
    result = classify_news_event(
        title="Micron beats earnings and raises guidance",
        content_snippet="Revenue growth was strong.",
    )

    assert result == {
        "sentiment": "positive",
        "topic": "earnings_guidance",
        "importance": "high",
    }


def test_build_news_summary_aggregates_recent_30_day_events():
    summary = build_news_summary(
        ticker="MU",
        news_events=[
            {
                "title": "Micron beats earnings",
                "source": "Reuters",
                    "published_at": datetime.now(UTC).isoformat(),
                "sentiment": "positive",
                "topic": "earnings_guidance",
                "importance": "high",
                "source_quality": "high",
                "url": "https://example.com/1",
            },
            {
                "title": "Old Micron article",
                "source": "Old Source",
                "published_at": "2026-04-01T00:00:00+00:00",
                "sentiment": "negative",
                "topic": "risk_event",
                "importance": "high",
                "source_quality": "medium",
                "url": "https://example.com/old",
            },
        ],
        now=parse_yfinance_datetime_to_datetime("2026-06-28T00:00:00Z"),
    )

    assert summary["status"] == "success"
    assert summary["total_events"] == 1
    assert summary["overall_sentiment"] == "positive"
    assert summary["dominant_topic"] == "earnings_guidance"
    assert summary["dominant_topic_label"] == "影響財報預期"
    assert summary["high_importance_count"] == 1


def test_build_news_summary_returns_no_recent_news():
    summary = build_news_summary(
        ticker="MU",
        news_events=[],
    )

    assert summary["status"] == "no_recent_news"
    assert summary["total_events"] == 0
    assert summary["overall_sentiment"] == "unknown"


def test_fetch_news_events_filters_by_ticker():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self):
            return json.dumps([{"ticker": "MU", "title": "Micron news"}]).encode(
                "utf-8"
            )

    def fake_open_url(request, timeout):
        assert "ticker=eq.MU" in request.full_url
        assert "order=published_at.desc" in request.full_url
        return FakeResponse()

    rows = fetch_news_events(
        ticker="MU",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert rows == [{"ticker": "MU", "title": "Micron news"}]


def test_news_agent_uses_news_events_summary_when_available(monkeypatch):
    monkeypatch.setattr(
        "agent.experts.news_agent.fetch_news_events",
        lambda ticker, limit=100: [
            {
                "ticker": ticker,
                "title": "Micron beats earnings and raises guidance",
                "source": "Reuters",
                "published_at": datetime.now(UTC).isoformat(),
                "sentiment": "positive",
                "topic": "earnings_guidance",
                "importance": "high",
                "source_quality": "high",
                "url": "https://example.com/mu",
            }
        ],
    )

    result = run_news_agent("MU", include_news=True)

    assert result["source"] == "news_events"
    assert result["news_analysis"]["summary"]["total_items"] == 1
    assert result["news_analysis"]["summary"]["sentiment"] == "positive"
    assert result["news_analysis"]["summary"]["top_topics"] == {"earnings_guidance": 1}
    assert result["news_events_summary"]["dominant_topic_label"] == "影響財報預期"


def test_news_agent_falls_back_when_news_events_are_unavailable(monkeypatch):
    def raise_fetch_error(ticker, limit=100):
        raise RuntimeError("missing Supabase")

    monkeypatch.setattr("agent.experts.news_agent.fetch_news_events", raise_fetch_error)
    monkeypatch.setattr(
        "agent.experts.news_agent.fetch_news_items",
        lambda ticker: [{"title": "Micron shares rise on AI demand"}],
    )

    result = run_news_agent("MU", include_news=True)

    assert result["source"] == "legacy_news_skill"
    assert result["news_analysis"]["summary"]["total_items"] == 1
    assert result["news_events_summary"]["status"] == "no_recent_news"


def test_rule_based_report_includes_news_events_summary():
    report = format_single_stock_analysis(
        make_single_stock_report_data(
            news_events_summary={
                "status": "success",
                "lookback_days": 30,
                "total_events": 1,
                "overall_sentiment": "positive",
                "dominant_topic_label": "影響財報預期",
                "high_importance_count": 1,
                "representative_events": [
                    {
                        "published_at": "2026-06-20T00:00:00+00:00",
                        "source": "Reuters",
                        "title": "Micron beats earnings",
                    }
                ],
            }
        )
    )

    assert "近 30 天新聞數：1" in report
    assert "新聞整體情緒：偏利多" in report
    assert "主要新聞主題：影響財報預期" in report
    assert "不會單獨改變結論" in report


def test_optional_llm_news_extractor_falls_back_without_client(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("NEWS_LLM_PROVIDER", "openrouter")

    result = classify_news_event_with_optional_llm(
        ticker="MU",
        title="Micron beats earnings and raises guidance",
        mode="llm",
        llm_client=None,
    )

    assert result["sentiment"] == "positive"
    assert result["topic"] == "earnings_guidance"
    assert result["extractor"]["mode_used"] == "rule_based"
    assert result["extractor"]["fallback_used"] is True


def test_news_event_rows_do_not_call_llm_during_ingestion(monkeypatch):
    monkeypatch.setenv("NEWS_EXTRACTOR_MODE", "llm")
    monkeypatch.setenv("NEWS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    rows = build_news_event_rows(
        ticker="MU",
        raw_items=[
            {
                "provider": "google_news_rss",
                "source": "Reuters",
                "source_type": "news_aggregator",
                "title": "Micron beats earnings and raises guidance",
                "content_snippet": "Revenue growth was strong.",
                "url": "https://example.com/mu-earnings",
                "published_at": "2026-06-26T13:00:00+00:00",
            }
        ],
    )

    assert rows[0]["extractor_mode"] == "rule_based"
    assert rows[0]["extraction_status"] == "success"


def test_optional_llm_news_extractor_accepts_valid_llm_result():
    class FakeClient:
        provider = "deepseek"
        model = "fake-news-model"

        def extract(self, *, ticker, title, content_snippet):
            return {
                "sentiment": "negative",
                "topic": "risk_event",
                "importance": "high",
                "summary": "這則新聞偏向風險事件。",
                "ticker_relevance": "high",
            }

    result = classify_news_event_with_optional_llm(
        ticker="MU",
        title="Micron faces regulatory probe",
        mode="llm",
        llm_client=FakeClient(),
    )

    assert result["sentiment"] == "negative"
    assert result["topic"] == "risk_event"
    assert result["summary"] == "這則新聞偏向風險事件。"
    assert result["extractor"]["mode_used"] == "llm"


def test_news_extraction_cache_skips_classified_events():
    event = {
        "extraction_status": "success",
        "sentiment": "positive",
        "topic": "earnings_guidance",
        "importance": "high",
        "ticker_relevance": "high",
    }

    assert is_news_event_classified(event) is True
    assert should_skip_event(event, only_unclassified=True, reclassify=False) is True
    assert should_skip_event(event, only_unclassified=True, reclassify=True) is False


def test_news_extraction_cache_reuses_duplicate_classification():
    cached_event = {
        "id": "cached",
        "duplicate_group_id": "group-1",
        "extraction_status": "success",
        "sentiment": "positive",
        "topic": "earnings_guidance",
        "importance": "high",
        "ticker_relevance": "high",
        "llm_summary": "這是一則財報相關新聞。",
        "extractor_mode": "llm",
        "extractor_provider": "openrouter",
        "extractor_model": "openai/gpt-5.4-mini",
    }
    new_event = {
        "id": "new",
        "duplicate_group_id": "group-1",
        "extraction_status": "unclassified",
        "sentiment": "unknown",
        "topic": "general",
        "importance": "unknown",
    }

    duplicate = find_cached_duplicate_classification(
        event=new_event,
        events=[new_event, cached_event],
    )
    update = build_duplicate_classification_update(new_event, duplicate)

    assert duplicate == cached_event
    assert update["sentiment"] == "positive"
    assert update["extraction_status"] == "skipped_duplicate"
    assert update["extractor_provider"] == "openrouter"
    assert update["escalation_status"] == "not_needed"


def test_build_extraction_update_records_llm_fallback_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("NEWS_LLM_PROVIDER", "openrouter")

    update = build_extraction_update(
        event={
            "ticker": "MU",
            "title": "Micron beats earnings and raises guidance",
            "content_snippet": "Revenue growth was strong.",
        },
        mode="llm",
    )

    assert update["sentiment"] == "positive"
    assert update["topic"] == "earnings_guidance"
    assert update["extractor_mode"] == "rule_based"
    assert update["extraction_status"] == "fallback_rule_based"
    assert update["extraction_error"]


def test_news_escalation_rules_are_conservative():
    low_relevance = should_escalate_news_event(
        event={"source_quality": "high"},
        update={
            "topic": "risk_event",
            "importance": "high",
            "sentiment": "negative",
            "ticker_relevance": "low",
        },
    )
    clear_high = should_escalate_news_event(
        event={"source_quality": "high"},
        update={
            "topic": "earnings_guidance",
            "importance": "high",
            "sentiment": "positive",
            "ticker_relevance": "high",
        },
    )
    unclear_high = should_escalate_news_event(
        event={"source_quality": "high"},
        update={
            "topic": "earnings_guidance",
            "importance": "high",
            "sentiment": "unknown",
            "ticker_relevance": "high",
        },
    )
    risk_event = should_escalate_news_event(
        event={"source_quality": "medium"},
        update={
            "topic": "risk_event",
            "importance": "high",
            "sentiment": "negative",
            "ticker_relevance": "medium",
        },
    )

    assert low_relevance == (False, "ticker_relevance_low")
    assert clear_high == (False, "clear_or_low_impact")
    assert unclear_high == (True, "high_importance_unclear")
    assert risk_event == (True, "risk_event")


def test_build_extraction_update_applies_escalation_when_needed():
    class PrimaryClient:
        provider = "openrouter"
        model = "openai/gpt-5.4-mini"

        def extract(self, *, ticker, title, content_snippet):
            return {
                "sentiment": "unknown",
                "topic": "earnings_guidance",
                "importance": "high",
                "summary": "初步摘要。",
                "ticker_relevance": "high",
            }

    class EscalationClient:
        provider = "openrouter"
        model = "openai/gpt-5.5"

        def extract(self, *, ticker, title, content_snippet):
            return {
                "sentiment": "positive",
                "topic": "earnings_guidance",
                "importance": "high",
                "summary": "升級模型判斷這是財報利多新聞。",
                "ticker_relevance": "high",
            }

    update = build_extraction_update(
        event={
            "ticker": "MU",
            "title": "Micron reports earnings",
            "content_snippet": "Revenue details were mixed.",
            "source_quality": "high",
        },
        mode="llm",
        llm_client=PrimaryClient(),
        escalation_enabled=True,
        escalation_client=EscalationClient(),
        escalation_model="openai/gpt-5.5",
    )

    assert update["sentiment"] == "positive"
    assert update["llm_summary"] == "升級模型判斷這是財報利多新聞。"
    assert update["escalated"] is True
    assert update["escalation_status"] == "success"
    assert update["escalation_reason"] == "high_importance_unclear"


def test_build_extraction_update_keeps_primary_when_escalation_fails():
    class PrimaryClient:
        provider = "openrouter"
        model = "openai/gpt-5.4-mini"

        def extract(self, *, ticker, title, content_snippet):
            return {
                "sentiment": "unknown",
                "topic": "risk_event",
                "importance": "high",
                "summary": "初步摘要。",
                "ticker_relevance": "medium",
            }

    class BrokenEscalationClient:
        provider = "openrouter"
        model = "openai/gpt-5.5"

        def extract(self, *, ticker, title, content_snippet):
            raise RuntimeError("model unavailable")

    update = build_extraction_update(
        event={
            "ticker": "MU",
            "title": "Micron faces investigation",
            "content_snippet": "Regulator probe reported.",
            "source_quality": "medium",
        },
        mode="llm",
        llm_client=PrimaryClient(),
        escalation_enabled=True,
        escalation_client=BrokenEscalationClient(),
        escalation_model="openai/gpt-5.5",
    )

    assert update["sentiment"] == "unknown"
    assert update["topic"] == "risk_event"
    assert update["escalated"] is False
    assert update["escalation_status"] == "failed"
    assert "model unavailable" in update["escalation_error"]


def test_news_extractor_uses_openrouter_from_env(monkeypatch):
    monkeypatch.setenv("NEWS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("NEWS_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "http://127.0.0.1:8001")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "market-agent")

    client = get_news_extractor_client_from_env()

    assert isinstance(client, OpenRouterNewsExtractorClient)
    assert client.provider == "openrouter"
    assert client.model == "openai/gpt-4.1-mini"
    assert client.site_url == "http://127.0.0.1:8001"
    assert client.app_name == "market-agent"


def make_single_stock_report_data(news_events_summary):
    return {
        "intent": "single_stock_analysis",
        "status": "success",
        "ticker": "MU",
        "query": "MU 現在適合進場嗎",
        "technical_analysis": {
            "current_price": 100,
            "ma10": 95,
            "ma20": 90,
            "ma50": 80,
            "is_above_ma20": True,
            "short_term_trend": "strong",
            "rsi14": 58,
            "macd": 1.2,
            "macd_signal": 1.0,
            "macd_histogram": 0.2,
            "momentum_state": "bullish_momentum",
        },
        "signals": {
            "breakout": {
                "is_breakout": False,
                "latest_close": 100,
                "previous_high": 110,
            },
            "volume_surge": {
                "is_volume_surge": False,
                "volume_ratio": 1.0,
                "surge_multiplier": 1.5,
            },
            "pullback": {
                "is_pullback": False,
                "distance_from_ma20": 0.05,
            },
        },
        "news": [],
        "news_analysis": {
            "summary": {
                "total_items": 1,
                "sentiment": "positive",
                "sentiment_counts": {"positive": 1},
                "top_topics": {"earnings_guidance": 1},
                "high_importance_count": 1,
            }
        },
        "fundamentals": {
            "status": "success",
            "summary": {
                "stance": "neutral",
                "positives": [],
                "risks": [],
            },
        },
        "research_profile": {
            "technical_score": 1,
            "news_score": 1,
            "fundamental_score": 0,
            "risk_score": 0,
            "combined_score": 2,
            "setup_quality": "neutral_positive",
            "risk_level": "low",
            "research_confidence": "medium",
            "evidence_quality": {
                "level": "medium",
                "reason": "測試用證據品質。",
            },
        },
        "agent_outputs": {
            "news": {
                "news_events_summary": news_events_summary,
            }
        },
    }


def parse_yfinance_datetime_to_datetime(value):
    from datetime import datetime

    return datetime.fromisoformat(parse_yfinance_datetime(value))
