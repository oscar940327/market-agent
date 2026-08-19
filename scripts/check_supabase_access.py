import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import resolve_supabase_credentials  # noqa: E402


DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "maintenance" / "supabase_preflight.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail fast when Supabase is unavailable or quota-restricted."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        base_url, api_key = resolve_supabase_credentials()
        request = Request(
            f"{base_url}/rest/v1/tickers?select=ticker&limit=1",
            method="GET",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=30) as response:
            response.read()
        report = {
            "status": "success",
            "checked_at": checked_at,
            "components": {
                "supabase_access": {
                    "status": "success",
                    "summary": "Supabase REST access is available.",
                }
            },
            "errors": [],
        }
        exit_code = 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        category = classify_http_failure(exc.code, body)
        message = f"Supabase preflight failed with HTTP {exc.code}: {body}"
        report = failure_report(
            checked_at=checked_at,
            category=category,
            message=message,
        )
        exit_code = 1
    except Exception as exc:
        report = failure_report(
            checked_at=checked_at,
            category="supabase_connection",
            message=f"Supabase preflight failed: {exc}",
        )
        exit_code = 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"supabase_preflight={report['status']}")
    print(f"category={report.get('category', 'none')}")
    if report.get("errors"):
        print(f"message={report['errors'][0]['message']}")
    print(f"report={output_path}")
    return exit_code


def classify_http_failure(status_code: int, body: str) -> str:
    normalized = body.lower()
    if status_code == 402 or "exceed_egress_quota" in normalized:
        return "supabase_quota"
    if status_code in {401, 403}:
        return "configuration"
    return "supabase_connection"


def failure_report(*, checked_at: str, category: str, message: str) -> dict:
    return {
        "status": "failed",
        "checked_at": checked_at,
        "category": category,
        "components": {
            "supabase_access": {
                "status": "failed",
                "summary": message,
            }
        },
        "errors": [
            {
                "step": "supabase_preflight",
                "status": "failed",
                "message": message,
            }
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
