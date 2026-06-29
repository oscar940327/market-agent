import pandas as pd

from ml_returns import build_historical_return_reference


def make_return_dataset():
    rows = []
    for index in range(80):
        rows.append(
            {
                "ticker": "MU",
                "date": f"2022-01-{(index % 28) + 1:02d}",
                "market_regime": "bull",
                "is_breakout": index % 3 == 0,
                "is_volume_surge": False,
                "is_pullback": False,
                "rsi_14": 60,
                "volatility_20d": 0.03,
                "price_vs_ma20": 0.04,
                "forward_return_5d": -0.02 + index * 0.001,
                "forward_return_10d": -0.03 + index * 0.001,
                "forward_return_20d": -0.04 + index * 0.001,
                "max_drop_20d": -0.12 + index * 0.001,
            }
        )
    rows.append(
        {
            "ticker": "MU",
            "date": "2022-04-15",
            "market_regime": "bull",
            "is_breakout": True,
            "is_volume_surge": False,
            "is_pullback": False,
            "rsi_14": 61,
            "volatility_20d": 0.03,
            "price_vs_ma20": 0.03,
            "forward_return_5d": 0.05,
            "forward_return_10d": 0.06,
            "forward_return_20d": 0.07,
            "max_drop_20d": -0.05,
        }
    )
    return pd.DataFrame(rows)


def test_historical_return_reference_uses_past_similar_samples():
    dataset = make_return_dataset()
    feature_row = dataset.iloc[-1].to_dict()

    result = build_historical_return_reference(
        feature_row=feature_row,
        dataset=dataset,
        min_sample_size=10,
    )

    assert result["method"] == "historical_quantile_reference"
    assert result["sample_size"] >= 10
    assert result["similarity_scope"] == "same_ticker_same_regime_same_signal"
    assert result["evidence_quality"] in {"low", "low_to_medium", "medium", "high"}
    assert result["historical_average_return_5d"] is not None
    assert result["expected_return_range_5d"]["low"] < result[
        "expected_return_range_5d"
    ]["high"]
    assert result["upside_return_range_20d"]["low"] > 0
    assert result["max_drop_range_20d"]["high"] <= 0


def test_historical_return_reference_falls_back_when_exact_sample_is_small():
    dataset = make_return_dataset()
    feature_row = {
        **dataset.iloc[-1].to_dict(),
        "ticker": "NVDA",
        "market_regime": "bear",
    }

    result = build_historical_return_reference(
        feature_row=feature_row,
        dataset=dataset,
        min_sample_size=30,
    )

    assert result["similarity_scope"] == "full_historical_dataset"
    assert result["sample_size"] == 80
