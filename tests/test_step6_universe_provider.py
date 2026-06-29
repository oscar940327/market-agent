import json

from data_providers.universe_provider import (
    NASDAQ100_PROVIDER,
    build_missing_metadata_rows,
    fetch_nasdaq100_components,
    normalize_universe_record,
    parse_nasdaq100_components_html,
)
from data_store.supabase_store import chunk_records


SAMPLE_HTML = """
<table class="wikitable sortable">
  <tbody>
    <tr>
      <th>Ticker</th>
      <th>Company</th>
      <th>ICB Industry</th>
      <th>ICB Subsector</th>
    </tr>
    <tr>
      <td>MU</td>
      <td>Micron Technology</td>
      <td>Technology</td>
      <td>Semiconductors</td>
    </tr>
    <tr>
      <td>NVDA</td>
      <td>Nvidia</td>
      <td>Technology</td>
      <td>Semiconductors</td>
    </tr>
  </tbody>
</table>
"""


def test_parse_nasdaq100_components_html_finds_component_table():
    components = parse_nasdaq100_components_html(SAMPLE_HTML)

    assert components == [
        {
            "ticker": "MU",
            "name": "Micron Technology",
            "industry": "Technology",
        },
        {
            "ticker": "NVDA",
            "name": "Nvidia",
            "industry": "Technology",
        },
    ]


def test_fetch_nasdaq100_components_reports_provider_error():
    def failing_open_url(request, timeout):
        raise OSError("network unavailable")

    result = fetch_nasdaq100_components(open_url=failing_open_url)

    assert result.status == "provider_error"
    assert result.provider == NASDAQ100_PROVIDER
    assert result.records == []
    assert result.errors[0]["message"] == "network unavailable"


def test_normalize_universe_record_adds_metadata_and_local_themes():
    record = normalize_universe_record(
        component={
            "ticker": "MU",
            "name": "Micron Technology",
            "industry": "Technology",
        },
        fetched_at="2026-06-27T00:00:00+00:00",
    )

    assert record["ticker"] == "MU"
    assert record["universe"] == "QQQ100"
    assert record["universe_provider"] == NASDAQ100_PROVIDER
    assert "memory" in record["themes"]
    assert "semiconductor" in record["themes"]


def test_missing_metadata_report_marks_unmapped_theme_tickers():
    rows = build_missing_metadata_rows(
        [
            {
                "ticker": "ABC",
                "name": "Example",
                "industry": "Technology",
                "themes": [],
                "universe_provider": NASDAQ100_PROVIDER,
            },
            {
                "ticker": "MU",
                "name": "Micron Technology",
                "industry": "Technology",
                "themes": ["memory"],
                "universe_provider": NASDAQ100_PROVIDER,
            },
        ]
    )

    assert rows == [
        {
            "ticker": "ABC",
            "missing_fields": "themes",
            "name": "Example",
            "industry": "Technology",
            "themes": "",
            "universe_provider": NASDAQ100_PROVIDER,
        }
    ]


def test_chunk_records_splits_supabase_payloads():
    records = [{"ticker": str(index)} for index in range(5)]

    assert chunk_records(records, 2) == [
        [{"ticker": "0"}, {"ticker": "1"}],
        [{"ticker": "2"}, {"ticker": "3"}],
        [{"ticker": "4"}],
    ]


def test_supabase_payload_records_are_json_serializable():
    record = normalize_universe_record(
        component={
            "ticker": "NVDA",
            "name": "Nvidia",
            "industry": "Technology",
        },
        fetched_at="2026-06-27T00:00:00+00:00",
    )

    payload = json.dumps([record])

    assert '"ticker": "NVDA"' in payload
