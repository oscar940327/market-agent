import json

import agent.experts.fundamental_agent as fundamental_agent
from data_store.supabase_store import (
    fetch_latest_fundamental_snapshot,
    upsert_fundamental_snapshots,
)
from scripts.ingest_fundamentals import build_fundamental_snapshot_record
from scripts.run_daily_pipeline import build_parser, build_pipeline_steps


def parse_args(values):
    return build_parser().parse_args(values)


def test_fetch_latest_fundamental_snapshot_queries_latest_success_row():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "ticker": "MU",
                        "as_of_date": "2026-07-05",
                        "provider": "yfinance",
                        "status": "success",
                        "forward_pe": 6.5,
                        "summary": {"stance": "positive"},
                    }
                ]
            ).encode("utf-8")

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    row = fetch_latest_fundamental_snapshot(
        ticker="MU",
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert row["ticker"] == "MU"
    assert row["forward_pe"] == 6.5
    assert "fundamental_snapshots?select=%2A" in captured["url"]
    assert "ticker=eq.MU" in captured["url"]
    assert "status=eq.success" in captured["url"]
    assert "order=as_of_date.desc%2Cfetched_at.desc" in captured["url"]


def test_upsert_fundamental_snapshots_uses_unique_conflict_key():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b""

    def fake_open_url(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    result = upsert_fundamental_snapshots(
        [{"ticker": "MU", "as_of_date": "2026-07-05", "provider": "yfinance"}],
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        open_url=fake_open_url,
    )

    assert result["status"] == "success"
    assert result["upserted_count"] == 1
    assert "on_conflict=ticker,as_of_date,provider" in captured["url"]
    assert captured["body"][0]["ticker"] == "MU"


def test_fundamental_agent_prefers_supabase_snapshot(monkeypatch):
    def fake_snapshot(ticker):
        return {
            "ticker": ticker,
            "as_of_date": "2026-07-05",
            "provider": "yfinance",
            "status": "success",
            "forward_pe": 7.1,
            "revenue_growth": 0.2,
            "earnings_growth": 0.3,
            "gross_margins": 0.5,
            "summary": {"stance": "positive", "positives": ["cached"], "risks": []},
            "fetched_at": "2026-07-05T00:00:00+00:00",
        }

    def fail_provider(ticker):
        raise AssertionError("provider should not be called when Supabase has data")

    monkeypatch.setattr(fundamental_agent, "fetch_latest_fundamental_snapshot", fake_snapshot)
    monkeypatch.setattr(fundamental_agent, "get_basic_fundamentals", fail_provider)

    result = fundamental_agent.fetch_fundamentals("MU")

    assert result["status"] == "success"
    assert result["provider"] == "supabase_fundamental_snapshots"
    assert result["source_provider"] == "yfinance"
    assert result["metrics"]["forward_pe"] == 7.1
    assert result["summary"]["positives"] == ["cached"]


def test_build_fundamental_snapshot_record_maps_metrics():
    record = build_fundamental_snapshot_record(
        ticker="mu",
        provider="yfinance",
        now=__import__("datetime").datetime(2026, 7, 5, tzinfo=__import__("datetime").UTC),
        fundamentals={
            "status": "success",
            "metrics": {
                "forward_pe": 6.5,
                "revenue_growth": 3.457,
                "sector": "Technology",
            },
            "summary": {"stance": "positive"},
        },
    )

    assert record["ticker"] == "MU"
    assert record["as_of_date"] == "2026-07-05"
    assert record["forward_pe"] == 6.5
    assert record["raw_metrics"]["revenue_growth"] == 3.457
    assert record["summary"]["stance"] == "positive"


def test_pipeline_has_fundamentals_slice():
    steps = build_pipeline_steps(parse_args(["--only", "fundamentals", "--tickers", "MU"]))

    assert [step.name for step in steps] == ["fundamentals"]
    assert "ingest_fundamentals.py" in steps[0].command[1]
    assert "--tickers" in steps[0].command
    assert "MU" in steps[0].command
