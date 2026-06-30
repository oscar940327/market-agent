import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


def upsert_tickers(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 100,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = f"{base_url}/rest/v1/tickers?on_conflict=ticker,universe"
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=30) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def fetch_active_tickers(
    *,
    universe: str = "QQQ100",
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
) -> list[str]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    endpoint = (
        f"{base_url}/rest/v1/tickers?"
        f"select=ticker&universe=eq.{universe}&is_active=eq.true&order=ticker.asc"
    )
    request = Request(
        endpoint,
        method="GET",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    with open_url(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8"))

    return [row["ticker"] for row in rows]


def upsert_daily_prices(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 500,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = f"{base_url}/rest/v1/daily_prices?on_conflict=ticker,date,provider"
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=60) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def fetch_daily_prices(
    *,
    ticker: str,
    provider: str = "yfinance",
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    page_size: int = 1000,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    rows = []
    offset = 0

    while True:
        endpoint = (
            f"{base_url}/rest/v1/daily_prices?"
            "select=date,open,high,low,close,volume,provider"
            f"&ticker=eq.{ticker.upper()}&provider=eq.{provider}"
            f"&order=date.asc&limit={page_size}&offset={offset}"
        )
        request = Request(
            endpoint,
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with open_url(request, timeout=60) as response:
            page_rows = json.loads(response.read().decode("utf-8"))

        rows.extend(page_rows)

        if len(page_rows) < page_size:
            return rows

        offset += page_size


def fetch_technical_features(
    *,
    ticker: str,
    price_provider: str = "yfinance",
    feature_version: str = "v1",
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    page_size: int = 1000,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    rows = []
    offset = 0

    while True:
        endpoint = (
            f"{base_url}/rest/v1/technical_features?"
            "select=ticker,date,price_provider,close,volume,ma5,ma10,ma20,ma50,"
            "ma200,rsi_14,macd,macd_signal,macd_histogram,short_term_trend,"
            "momentum_state,is_breakout,is_volume_surge,is_pullback,feature_version"
            f"&ticker=eq.{ticker.upper()}&price_provider=eq.{price_provider}"
            f"&feature_version=eq.{feature_version}"
            f"&order=date.asc&limit={page_size}&offset={offset}"
        )
        request = Request(
            endpoint,
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with open_url(request, timeout=60) as response:
            page_rows = json.loads(response.read().decode("utf-8"))

        rows.extend(page_rows)

        if len(page_rows) < page_size:
            return rows

        offset += page_size


def upsert_technical_features(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 500,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = (
            f"{base_url}/rest/v1/technical_features?"
            "on_conflict=ticker,date,price_provider,feature_version"
        )
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=60) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def upsert_market_regimes(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 500,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = f"{base_url}/rest/v1/market_regimes?on_conflict=date,benchmark,rule_version"
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=60) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def upsert_news_event_summaries(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 100,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = (
            f"{base_url}/rest/v1/news_event_summaries?"
            "on_conflict=ticker,summary_date,window_days,provider"
        )
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=30) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def fetch_market_regimes(
    *,
    benchmark: str = "QQQ",
    rule_version: str = "v1",
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    page_size: int = 1000,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    rows = []
    offset = 0

    while True:
        endpoint = (
            f"{base_url}/rest/v1/market_regimes?"
            "select=date,benchmark,regime,close,ma200,three_month_return,"
            "regime_changed,previous_regime,rule_version,data_as_of"
            f"&benchmark=eq.{benchmark.upper()}&rule_version=eq.{rule_version}"
            f"&order=date.asc&limit={page_size}&offset={offset}"
        )
        request = Request(
            endpoint,
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with open_url(request, timeout=60) as response:
            page_rows = json.loads(response.read().decode("utf-8"))

        rows.extend(page_rows)

        if len(page_rows) < page_size:
            return rows

        offset += page_size


def insert_research_log(
    row: dict,
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
) -> dict:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    endpoint = f"{base_url}/rest/v1/research_logs"
    payload = json.dumps(row).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )

    try:
        with open_url(request, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "message": f"Supabase insert failed with HTTP {exc.code}: {body}",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Supabase insert failed: {exc}"}

    return {"status": "success", "row": rows[0] if rows else None}


def upsert_research_outcomes(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    chunk_size: int = 100,
) -> dict:
    if not records:
        return {"status": "skipped", "upserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    total_count = 0

    for chunk in chunk_records(records, chunk_size):
        endpoint = (
            f"{base_url}/rest/v1/research_outcomes?"
            "on_conflict=research_log_id,horizon_trading_days"
        )
        payload = json.dumps(chunk, allow_nan=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

        try:
            with open_url(request, timeout=30) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "upserted_count": total_count,
                "message": f"Supabase upsert failed: {exc}",
            }

        total_count += len(chunk)

    return {"status": "success", "upserted_count": total_count}


def insert_news_events(
    records: list[dict],
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
) -> dict:
    if not records:
        return {"status": "skipped", "inserted_count": 0, "message": "No records."}

    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    inserted_count = 0
    duplicate_count = 0

    for record in records:
        endpoint = f"{base_url}/rest/v1/news_events"
        payload = json.dumps(record).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )

        try:
            with open_url(request, timeout=30) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 409:
                duplicate_count += 1
                continue

            return {
                "status": "error",
                "inserted_count": inserted_count,
                "duplicate_count": duplicate_count,
                "message": f"Supabase insert failed with HTTP {exc.code}: {body}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "inserted_count": inserted_count,
                "duplicate_count": duplicate_count,
                "message": f"Supabase insert failed: {exc}",
            }

        inserted_count += 1

    return {
        "status": "success",
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
    }


def fetch_news_events(
    *,
    ticker: str | None = None,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    limit: int = 100,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    endpoint = (
        f"{base_url}/rest/v1/news_events?"
        "select=id,ticker,source,source_type,title,content_snippet,url,published_at,"
        "sentiment,topic,importance,source_quality,duplicate_group_id,"
        "ticker_mapping_confidence,extractor_mode,extractor_provider,extractor_model,"
        "extracted_at,extraction_status,llm_summary,ticker_relevance,extraction_error,"
        "escalation_enabled,escalated,escalation_model,escalation_reason,"
        "escalation_status,escalation_error"
        f"{build_optional_ticker_filter(ticker)}&order=published_at.desc&limit={limit}"
    )
    request = Request(
        endpoint,
        method="GET",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    with open_url(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_news_events_for_dataset(
    *,
    ticker: str,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    page_size: int = 1000,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    rows = []
    offset = 0

    while True:
        endpoint = (
            f"{base_url}/rest/v1/news_events?"
            "select=ticker,published_at,sentiment,topic,importance,source_quality,"
            "ticker_relevance"
            f"&ticker=eq.{ticker.upper()}"
            f"&order=published_at.asc&limit={page_size}&offset={offset}"
        )
        request = Request(
            endpoint,
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with open_url(request, timeout=60) as response:
            page_rows = json.loads(response.read().decode("utf-8"))

        rows.extend(page_rows)

        if len(page_rows) < page_size:
            return rows

        offset += page_size


def update_news_event_classification(
    *,
    event_id: str,
    sentiment: str,
    topic: str,
    importance: str,
    source_quality: str | None = None,
    ticker_relevance: str | None = None,
    llm_summary: str | None = None,
    extractor_mode: str | None = None,
    extractor_provider: str | None = None,
    extractor_model: str | None = None,
    extracted_at: str | None = None,
    extraction_status: str | None = None,
    extraction_error: str | None = None,
    escalation_enabled: bool | None = None,
    escalated: bool | None = None,
    escalation_model: str | None = None,
    escalation_reason: str | None = None,
    escalation_status: str | None = None,
    escalation_error: str | None = None,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
) -> dict:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    endpoint = f"{base_url}/rest/v1/news_events?id=eq.{event_id}"
    payload = {
        "sentiment": sentiment,
        "topic": topic,
        "importance": importance,
    }
    if source_quality:
        payload["source_quality"] = source_quality
    optional_fields = {
        "ticker_relevance": ticker_relevance,
        "llm_summary": llm_summary,
        "extractor_mode": extractor_mode,
        "extractor_provider": extractor_provider,
        "extractor_model": extractor_model,
        "extracted_at": extracted_at,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error,
        "escalation_enabled": escalation_enabled,
        "escalated": escalated,
        "escalation_model": escalation_model,
        "escalation_reason": escalation_reason,
        "escalation_status": escalation_status,
        "escalation_error": escalation_error,
    }
    payload.update(
        {
            key: value
            for key, value in optional_fields.items()
            if value is not None
        }
    )

    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )

    try:
        with open_url(request, timeout=30) as response:
            response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "message": f"Supabase update failed with HTTP {exc.code}: {body}",
        }
    except Exception as exc:
        return {"status": "error", "message": f"Supabase update failed: {exc}"}

    return {"status": "success"}


def fetch_pending_research_outcomes(
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    limit: int = 100,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    endpoint = (
        f"{base_url}/rest/v1/research_outcomes?"
        "select=research_log_id,ticker,query_date,horizon_trading_days,"
        "price_at_query,price_provider"
        f"&outcome_status=eq.pending&order=query_date.asc&limit={limit}"
    )
    request = Request(
        endpoint,
        method="GET",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    with open_url(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_similar_case_results(
    *,
    ticker: str,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
    page_size: int = 1000,
) -> list[dict]:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    rows = []
    offset = 0

    while True:
        endpoint = (
            f"{base_url}/rest/v1/similar_case_results?"
            "select=query_ticker,query_date,scope,relaxation_step,technical_pattern,"
            "news_event_type,market_regime,sample_size,win_rate_5d,win_rate_10d,"
            "win_rate_20d,average_forward_return_20d,max_loss_20d,"
            "evidence_quality,source_data_as_of,result_status"
            f"&query_ticker=eq.{ticker.upper()}"
            f"&order=query_date.asc&limit={page_size}&offset={offset}"
        )
        request = Request(
            endpoint,
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

        with open_url(request, timeout=60) as response:
            page_rows = json.loads(response.read().decode("utf-8"))

        rows.extend(page_rows)

        if len(page_rows) < page_size:
            return rows

        offset += page_size


def build_optional_ticker_filter(ticker: str | None) -> str:
    if not ticker:
        return ""

    return f"&ticker=eq.{ticker.upper()}"


def fetch_latest_date(
    *,
    table: str,
    date_column: str = "date",
    filters: dict[str, str] | None = None,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    open_url=urlopen,
) -> str | None:
    base_url, api_key = resolve_supabase_credentials(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
    query = {
        "select": date_column,
        "order": f"{date_column}.desc",
        "limit": "1",
    }
    if filters:
        query.update(filters)

    endpoint = f"{base_url}/rest/v1/{table}?{urlencode(query)}"
    request = Request(
        endpoint,
        method="GET",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    with open_url(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8"))

    if not rows:
        return None

    return rows[0].get(date_column)


def resolve_supabase_credentials(
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> tuple[str, str]:
    load_dotenv()
    base_url = (supabase_url or os.getenv("SUPABASE_URL") or "").rstrip("/")
    api_key = (
        supabase_key
        or os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )

    if not base_url:
        raise RuntimeError("Missing SUPABASE_URL.")
    if not api_key:
        raise RuntimeError("Missing SUPABASE_SECRET_KEY.")

    return base_url, api_key


def chunk_records(records: list[dict], chunk_size: int) -> list[list[dict]]:
    return [
        records[index : index + chunk_size]
        for index in range(0, len(records), chunk_size)
    ]
