from data_store import fetch_latest_fundamental_snapshot
from skills.fundamental_skill import get_basic_fundamentals, summarize_fundamentals


SKIPPED_FUNDAMENTALS = {
    "status": "skipped",
    "provider": None,
    "metrics": {},
    "summary": {
        "stance": "unknown",
        "positives": [],
        "risks": [],
    },
}


STATIC_FUNDAMENTAL_FALLBACKS = {
    "MU": {
        "status": "success",
        "provider": "static_fallback",
        "as_of": "2026-07-05",
        "metrics": {
            "market_cap": None,
            "trailing_pe": None,
            "forward_pe": 6.5,
            "price_to_sales": None,
            "revenue_growth": 3.457,
            "earnings_growth": 13.685,
            "gross_margins": 0.726,
            "operating_margins": None,
            "profit_margins": None,
            "free_cashflow": None,
            "debt_to_equity": None,
            "earnings_date": None,
            "sector": "Technology",
            "industry": "Semiconductors",
        },
        "summary": {
            "stance": "positive",
            "positives": [
                "營收成長為正",
                "獲利成長為正",
                "毛利率相對較高",
            ],
            "risks": [],
        },
        "fallback_reason": "yfinance fundamental data was unavailable at request time.",
    }
}


def get_static_fundamental_fallback(ticker: str) -> dict | None:
    fallback = STATIC_FUNDAMENTAL_FALLBACKS.get(ticker.upper())
    if not fallback:
        return None

    return {
        **fallback,
        "metrics": {**fallback["metrics"]},
        "summary": {
            **fallback["summary"],
            "positives": list(fallback["summary"].get("positives", [])),
            "risks": list(fallback["summary"].get("risks", [])),
        },
    }


def fetch_supabase_fundamentals(ticker: str) -> dict | None:
    try:
        snapshot = fetch_latest_fundamental_snapshot(ticker=ticker)
    except Exception:
        return None

    if not snapshot:
        return None

    return build_fundamentals_from_snapshot(snapshot)


def build_fundamentals_from_snapshot(snapshot: dict) -> dict:
    metrics = {
        "market_cap": snapshot.get("market_cap"),
        "trailing_pe": snapshot.get("trailing_pe"),
        "forward_pe": snapshot.get("forward_pe"),
        "price_to_sales": snapshot.get("price_to_sales"),
        "revenue_growth": snapshot.get("revenue_growth"),
        "earnings_growth": snapshot.get("earnings_growth"),
        "gross_margins": snapshot.get("gross_margins"),
        "operating_margins": snapshot.get("operating_margins"),
        "profit_margins": snapshot.get("profit_margins"),
        "free_cashflow": snapshot.get("free_cashflow"),
        "debt_to_equity": snapshot.get("debt_to_equity"),
        "earnings_date": snapshot.get("earnings_date"),
        "sector": snapshot.get("sector"),
        "industry": snapshot.get("industry"),
    }
    summary = snapshot.get("summary") or summarize_fundamentals(metrics)

    return {
        "status": "success",
        "provider": "supabase_fundamental_snapshots",
        "source_provider": snapshot.get("provider"),
        "as_of": snapshot.get("as_of_date"),
        "fetched_at": snapshot.get("fetched_at"),
        "metrics": metrics,
        "summary": summary,
    }


def fetch_fundamentals(ticker: str) -> dict:
    supabase_fundamentals = fetch_supabase_fundamentals(ticker)
    if supabase_fundamentals:
        return supabase_fundamentals

    try:
        return get_basic_fundamentals(ticker)
    except Exception as error:
        fallback = get_static_fundamental_fallback(ticker)
        if fallback:
            fallback["provider_error"] = str(error)
            return fallback

        return {
            "status": "fundamental_data_error",
            "provider": "yfinance",
            "message": f"取得基本面資料時發生錯誤：{error}",
            "metrics": {},
            "summary": {
                "stance": "unknown",
                "positives": [],
                "risks": ["基本面資料暫時無法取得"],
            },
        }


def run_fundamental_agent(ticker: str, include_fundamentals: bool = True) -> dict:
    if include_fundamentals:
        fundamentals = fetch_fundamentals(ticker)
    else:
        fundamentals = {
            **SKIPPED_FUNDAMENTALS,
            "summary": {
                **SKIPPED_FUNDAMENTALS["summary"],
                "positives": [],
                "risks": [],
            },
        }

    summary = fundamentals["summary"]

    return {
        "agent": "fundamental",
        "status": fundamentals["status"],
        "fundamentals": fundamentals,
        "summary": {
            "stance": summary["stance"],
            "positives": summary.get("positives", []),
            "risks": summary.get("risks", []),
        },
    }
