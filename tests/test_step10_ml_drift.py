import json

import pandas as pd

from ml_monitoring import build_drift_report, build_drift_summary_markdown
from scripts import build_ml_drift_report as script


def make_dataset() -> pd.DataFrame:
    baseline_rows = []
    for index in range(40):
        baseline_rows.append(
            {
                "ticker": "MU",
                "date": f"2026-01-{(index % 28) + 1:02d}",
                "rsi_14": 50,
                "macd_histogram": 0.1,
                "return_5d": 0.01,
                "return_10d": 0.01,
                "return_20d": 0.02,
                "volatility_20d": 0.03,
                "volume_ratio_20d": 1.0,
                "price_vs_ma20": 0.02,
                "price_vs_ma50": 0.03,
                "price_vs_ma200": 0.05,
                "news_sentiment_score_30d": 0.1,
                "news_count_30d": 10,
                "news_missing": False,
                "market_regime": "bull",
                "qqq_above_ma200": True,
                "regime_changed": False,
            }
        )
    recent_rows = []
    for index in range(10):
        recent_rows.append(
            {
                **baseline_rows[0],
                "date": f"2026-06-{20 + index:02d}",
                "rsi_14": 80,
                "news_count_30d": 2,
                "news_missing": index < 5,
                "qqq_above_ma200": False,
                "regime_changed": index == 9,
            }
        )
    return pd.DataFrame(baseline_rows + recent_rows)


def test_build_drift_report_detects_feature_market_news_and_freshness_warnings():
    report = build_drift_report(
        make_dataset(),
        recent_days=30,
        baseline_days=365,
        freshness_report={
            "overall": "stale",
            "daily_prices": {"status": "stale"},
            "technical_features": {"status": "fresh"},
        },
    )

    warning_sources = {warning["source"] for warning in report["warnings"]}
    assert "feature_drift" in warning_sources
    assert "market_regime_drift" in warning_sources
    assert "news_coverage_drift" in warning_sources
    assert "data_freshness" in warning_sources
    assert report["market_regime_drift"]["latest_qqq_above_ma200"] is False
    assert report["news_coverage_drift"]["recent_news_missing_ratio"] == 0.5
    assert report["alert"]["should_alert"] is True


def test_build_drift_report_handles_clean_dataset_without_warnings():
    dataset = make_dataset()
    dataset.loc[dataset["date"].str.startswith("2026-06"), "rsi_14"] = 50
    dataset.loc[dataset["date"].str.startswith("2026-06"), "news_count_30d"] = 10
    dataset.loc[dataset["date"].str.startswith("2026-06"), "news_missing"] = False
    dataset.loc[dataset["date"].str.startswith("2026-06"), "qqq_above_ma200"] = True
    dataset.loc[dataset["date"].str.startswith("2026-06"), "regime_changed"] = False

    report = build_drift_report(
        dataset,
        recent_days=30,
        baseline_days=365,
        freshness_report={"overall": "fresh", "daily_prices": {"status": "fresh"}},
    )

    assert report["warnings"] == []
    assert report["alert"]["should_alert"] is False


def test_news_coverage_improvement_is_observation_not_harmful_drift():
    dataset = make_dataset()
    baseline_mask = dataset["date"].str.startswith("2026-01")
    recent_mask = dataset["date"].str.startswith("2026-06")
    dataset.loc[baseline_mask, "news_missing"] = True
    dataset.loc[baseline_mask, "news_count_30d"] = 0
    dataset.loc[recent_mask, "news_missing"] = dataset.loc[recent_mask].index % 2 == 0
    dataset.loc[recent_mask, "news_count_30d"] = 4
    dataset.loc[recent_mask, "rsi_14"] = 50
    dataset.loc[recent_mask, "qqq_above_ma200"] = True
    dataset.loc[recent_mask, "regime_changed"] = False

    report = build_drift_report(dataset, recent_days=30, baseline_days=365)

    assert not any(
        warning["source"] in {"feature_drift", "news_coverage_drift"}
        for warning in report["warnings"]
    )
    assert any(item["metric"] == "news_count_30d" for item in report["observations"])
    assert report["news_coverage_drift"]["baseline_news_missing_ratio"] == 1.0


def test_build_drift_summary_markdown_includes_sections():
    report = build_drift_report(make_dataset(), recent_days=30, baseline_days=365)

    markdown = build_drift_summary_markdown(report)

    assert "# ML Drift Report" in markdown
    assert "## Feature Drift" in markdown
    assert "## Market Regime" in markdown
    assert "## News Coverage" in markdown
    assert "## Warnings" in markdown


def test_build_ml_drift_report_script_writes_json_and_markdown(tmp_path):
    dataset_path = tmp_path / "training_dataset_v1.csv"
    make_dataset().to_csv(dataset_path, index=False)

    result = script.main(
        [
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(tmp_path),
            "--recent-days",
            "30",
            "--baseline-days",
            "365",
            "--skip-freshness",
        ]
    )

    json_path = tmp_path / "ml_drift_report_30d_vs_365d_v1.json"
    markdown_path = tmp_path / "ml_drift_summary_30d_vs_365d_v1.md"

    assert result == 0
    assert json_path.exists()
    assert markdown_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["recent_days"] == 30
    assert report["baseline_days"] == 365


def test_build_ml_drift_report_script_handles_missing_dataset(tmp_path):
    missing_dataset_path = tmp_path / "missing_training_dataset.csv"

    result = script.main(
        [
            "--dataset-path",
            str(missing_dataset_path),
            "--output-dir",
            str(tmp_path),
            "--recent-days",
            "30",
            "--baseline-days",
            "365",
            "--skip-freshness",
        ]
    )

    json_path = tmp_path / "ml_drift_report_30d_vs_365d_v1.json"
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert result == 0
    assert report["status"] == "unavailable"
    assert report["dataset_rows"] == 0
    assert report["alert"]["reason"] == "drift_dataset_unavailable"
    assert report["warnings"][0]["source"] == "dataset"
