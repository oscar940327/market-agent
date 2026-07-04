import json
import subprocess

import scripts.run_daily_pipeline as daily_pipeline
from scripts.run_daily_pipeline import (
    build_parser,
    build_pipeline_steps,
    parse_step_metrics,
    run_pipeline,
)
from scripts.summarize_news_events import build_news_summary_record


def parse_args(values):
    return build_parser().parse_args(values)


def test_price_only_dry_run_includes_freshness_and_writes_log(tmp_path):
    args = parse_args(["--only", "prices", "--limit", "3", "--dry-run", "--log-dir", str(tmp_path)])

    log = run_pipeline(args)

    assert log["status"] == "success"
    assert [step["name"] for step in log["steps"]] == [
        "benchmark_prices",
        "daily_prices",
        "benchmark_technical_features",
        "technical_features",
        "market_regimes",
        "freshness_check",
    ]
    assert all(step["status"] == "dry_run" for step in log["steps"])
    freshness_step = next(step for step in log["steps"] if step["name"] == "freshness_check")
    assert "--scope" in freshness_step["command"]
    assert "prices" in freshness_step["command"]
    assert "daily_pipeline_" in log["log_path"]
    assert log["latest_log_path"].endswith("latest_daily_pipeline.json")
    assert json.loads((tmp_path / log["log_path"].split("\\")[-1]).read_text(encoding="utf-8"))["status"] == "success"
    assert json.loads((tmp_path / "latest_daily_pipeline.json").read_text(encoding="utf-8"))["status"] == "success"
    assert log["supabase_log"]["status"] == "skipped"


def test_pipeline_writes_run_summary_to_supabase_and_local_log(tmp_path, monkeypatch):
    args = parse_args(["--only", "prices", "--limit", "3", "--no-alert", "--log-dir", str(tmp_path)])
    captured = {}

    def fake_runner(command):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    def fake_insert_pipeline_run(row):
        captured["row"] = row
        return {"status": "success", "row": {"id": "pipeline-run-1"}}

    monkeypatch.setattr(daily_pipeline, "insert_pipeline_run", fake_insert_pipeline_run)

    log = run_pipeline(args, command_runner=fake_runner)
    latest_log = json.loads((tmp_path / "latest_daily_pipeline.json").read_text(encoding="utf-8"))

    assert log["status"] == "success"
    assert captured["row"]["pipeline"] == "daily"
    assert captured["row"]["status"] == "success"
    assert captured["row"]["options"]["only"] == "prices"
    assert captured["row"]["steps"][0]["name"] == "benchmark_prices"
    assert log["supabase_log"]["id"] == "pipeline-run-1"
    assert latest_log["supabase_log"]["id"] == "pipeline-run-1"


def test_skip_llm_news_uses_rule_based_classification():
    args = parse_args(["--only", "news", "--tickers", "MU", "--skip-llm-news"])

    steps = build_pipeline_steps(args)
    classify_step = next(step for step in steps if step.name == "news_classification")

    assert "--mode" in classify_step.command
    assert "rule_based" in classify_step.command


def test_news_failure_makes_pipeline_partial_success(tmp_path):
    args = parse_args(["--only", "all", "--tickers", "MU", "--log-dir", str(tmp_path)])
    calls = []

    def fake_runner(command):
        calls.append(command)
        script_name = command[1].split("\\")[-1].split("/")[-1]
        return subprocess.CompletedProcess(
            command,
            1 if script_name == "ingest_news_events.py" else 0,
            stdout="warning=news temporarily unavailable" if script_name == "ingest_news_events.py" else "ok",
            stderr="news unavailable" if script_name == "ingest_news_events.py" else "",
        )

    log = run_pipeline(args, command_runner=fake_runner)

    assert log["status"] == "partial_success"
    assert log["warnings"][0]["step"] == "news_ingestion"
    failed_step = next(step for step in log["steps"] if step["name"] == "news_ingestion")
    assert failed_step["attempts"] == 2
    assert failed_step["metrics"]["warning"] == "news temporarily unavailable"
    assert "news unavailable" in failed_step["stderr_tail"]
    assert len(calls) == len(log["steps"]) + 1


def test_core_failure_makes_pipeline_failed(tmp_path):
    args = parse_args(["--only", "prices", "--log-dir", str(tmp_path)])

    def fake_runner(command):
        script_name = command[1].split("\\")[-1].split("/")[-1]
        return subprocess.CompletedProcess(
            command,
            1 if script_name == "check_freshness.py" else 0,
            stdout="",
            stderr="stale data",
        )

    log = run_pipeline(args, command_runner=fake_runner)

    assert log["status"] == "failed"
    assert log["errors"][0]["step"] == "freshness_check"
    freshness = next(step for step in log["steps"] if step["name"] == "freshness_check")
    assert freshness["attempts"] == 1


def test_build_news_summary_record_maps_summary_to_supabase_row():
    record = build_news_summary_record(
        summary={
            "ticker": "MU",
            "lookback_days": 30,
            "total_events": 2,
            "overall_sentiment": "positive",
            "dominant_topic": "earnings_guidance",
            "dominant_topic_label": "影響財報預期",
            "high_importance_count": 1,
        },
        summary_date="2026-06-30",
        provider="market_agent",
        generated_at="2026-06-30T00:00:00+00:00",
    )

    assert record["ticker"] == "MU"
    assert record["summary_date"] == "2026-06-30"
    assert record["window_days"] == 30
    assert record["summary_json"]["total_events"] == 2


def test_parse_step_metrics_converts_key_value_stdout():
    metrics = parse_step_metrics(
        "\n".join(
            [
                "tickers=101",
                "supabase=success",
                "supabase_upserted=349804",
                "overall=fresh",
                "warning=news stale",
                "ratio=1.5",
            ]
        )
    )

    assert metrics["tickers"] == 101
    assert metrics["supabase"] == "success"
    assert metrics["supabase_upserted"] == 349804
    assert metrics["overall"] == "fresh"
    assert metrics["warning"] == "news stale"
    assert metrics["ratio"] == 1.5
