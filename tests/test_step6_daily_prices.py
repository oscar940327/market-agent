from datetime import date

import pandas as pd

from data_providers.price_history import (
    build_daily_price_records,
    build_price_ingest_plan,
    build_price_ingest_result,
    write_price_ingest_report,
)
from data_providers.price_service import PriceFetchResult
from data_store.supabase_store import chunk_records


def make_price_frame(start="2011-04-27", periods=3900):
    index = pd.bdate_range(start=start, periods=periods)
    return pd.DataFrame(
        {
            "Open": [100.0] * periods,
            "High": [101.0] * periods,
            "Low": [99.0] * periods,
            "Close": [100.5] * periods,
            "Volume": [1000000] * periods,
        },
        index=index,
    )


def test_build_price_ingest_plan_uses_15_year_window_plus_2_month_buffer():
    plan = build_price_ingest_plan(data_end_date=date(2026, 6, 27))

    assert plan.data_end_date == date(2026, 6, 27)
    assert plan.research_start_date == date(2011, 6, 27)
    assert plan.fetch_start_date == date(2011, 4, 27)
    assert plan.research_years == 15
    assert plan.buffer_months == 2


def test_build_price_ingest_result_marks_success_for_full_history():
    plan = build_price_ingest_plan(data_end_date=date(2026, 6, 27))
    fetch_result = PriceFetchResult(
        data=make_price_frame(),
        provider="yfinance",
        attempted_providers=["yfinance"],
    )

    result = build_price_ingest_result(
        ticker="MU",
        fetch_result=fetch_result,
        plan=plan,
    )

    assert result.status == "success"
    assert result.provider == "yfinance"
    assert result.data_start_date == "2011-04-27"
    assert result.research_start_date == "2011-06-27"
    assert result.fetch_start_date == "2011-04-27"
    assert result.row_count == 3900


def test_build_price_ingest_result_marks_insufficient_history_for_new_stock():
    plan = build_price_ingest_plan(data_end_date=date(2026, 6, 27))
    fetch_result = PriceFetchResult(
        data=make_price_frame(start="2021-01-01", periods=1200),
        provider="yfinance",
        attempted_providers=["yfinance"],
    )

    result = build_price_ingest_result(
        ticker="APP",
        fetch_result=fetch_result,
        plan=plan,
    )

    assert result.status == "insufficient_history"
    assert result.data_start_date == "2021-01-01"
    assert result.insufficient_reason == "listed_after_research_start"
    assert result.history_note == "目前 ticker 無 15 年價格資料"


def test_build_price_ingest_result_marks_no_price_data():
    plan = build_price_ingest_plan(data_end_date=date(2026, 6, 27))
    fetch_result = PriceFetchResult(
        data=pd.DataFrame(),
        provider=None,
        attempted_providers=["yfinance", "stooq"],
        errors=[{"provider": "yfinance", "message": "provider returned no price data"}],
    )

    result = build_price_ingest_result(
        ticker="MISSING",
        fetch_result=fetch_result,
        plan=plan,
    )

    assert result.status == "no_price_data"
    assert result.records == []
    assert result.errors[0]["message"] == "provider returned no price data"


def test_build_daily_price_records_matches_supabase_schema():
    price_data = make_price_frame(periods=1)

    records = build_daily_price_records(
        ticker="mu",
        provider="yfinance",
        price_data=price_data,
    )

    assert records[0]["ticker"] == "MU"
    assert records[0]["date"] == "2011-04-27"
    assert records[0]["open"] == 100.0
    assert records[0]["close"] == 100.5
    assert records[0]["volume"] == 1000000.0
    assert records[0]["provider"] == "yfinance"


def test_build_daily_price_records_skips_invalid_json_numbers():
    price_data = make_price_frame(periods=2)
    price_data.iloc[0, price_data.columns.get_loc("Open")] = float("nan")

    records = build_daily_price_records(
        ticker="mu",
        provider="yfinance",
        price_data=price_data,
    )

    assert len(records) == 1
    assert records[0]["date"] == "2011-04-28"


def test_write_price_ingest_report_writes_missing_rows(tmp_path):
    plan = build_price_ingest_plan(data_end_date=date(2026, 6, 27))
    full_result = build_price_ingest_result(
        ticker="MU",
        fetch_result=PriceFetchResult(
            data=make_price_frame(),
            provider="yfinance",
            attempted_providers=["yfinance"],
        ),
        plan=plan,
    )
    missing_result = build_price_ingest_result(
        ticker="MISSING",
        fetch_result=PriceFetchResult(
            data=pd.DataFrame(),
            provider=None,
            attempted_providers=["yfinance"],
        ),
        plan=plan,
    )
    listed_after_result = build_price_ingest_result(
        ticker="APP",
        fetch_result=PriceFetchResult(
            data=make_price_frame(start="2021-01-01", periods=1200),
            provider="yfinance",
            attempted_providers=["yfinance"],
        ),
        plan=plan,
    )

    report_path, missing_path = write_price_ingest_report(
        results=[full_result, missing_result, listed_after_result],
        output_dir=tmp_path,
        report_date="2026-06-27",
    )

    report_text = report_path.read_text(encoding="utf-8-sig")
    assert "MU" in report_text
    assert "APP" in report_text
    assert "目前 ticker 無 15 年價格資料" in report_text
    missing_text = missing_path.read_text(encoding="utf-8-sig")
    assert "MISSING" in missing_text
    assert "MU" not in missing_text
    assert "APP" not in missing_text


def test_daily_price_chunks_use_larger_batches():
    records = [{"ticker": str(index)} for index in range(1001)]

    chunks = chunk_records(records, 500)

    assert [len(chunk) for chunk in chunks] == [500, 500, 1]
