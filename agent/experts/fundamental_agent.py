from skills.fundamental_skill import get_basic_fundamentals


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


def fetch_fundamentals(ticker: str) -> dict:
    try:
        return get_basic_fundamentals(ticker)
    except Exception as error:
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
