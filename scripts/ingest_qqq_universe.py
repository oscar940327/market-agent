import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_providers.universe_provider import (  # noqa: E402
    fetch_nasdaq100_components,
    write_missing_metadata_report,
    write_universe_snapshot,
)
from data_store.supabase_store import upsert_tickers  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch QQQ100/Nasdaq-100 universe and upsert it to Supabase.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/market/universe",
        help="Directory for local CSV snapshot and missing metadata report.",
    )
    parser.add_argument(
        "--skip-supabase",
        action="store_true",
        help="Only write local CSV files. Do not write to Supabase.",
    )
    args = parser.parse_args()

    result = fetch_nasdaq100_components()
    if result.status != "success":
        print(f"status={result.status}")
        for error in result.errors:
            print(f"error={error.get('message')}")
        return 1

    snapshot_path = write_universe_snapshot(
        records=result.records,
        output_dir=args.output_dir,
    )
    missing_path, missing_rows = write_missing_metadata_report(
        records=result.records,
        output_dir=args.output_dir,
    )

    print(f"provider={result.provider}")
    print(f"records={len(result.records)}")
    print(f"snapshot={snapshot_path}")
    print(f"missing_metadata={missing_path}")
    print(f"missing_metadata_count={len(missing_rows)}")

    if args.skip_supabase:
        print("supabase=skipped")
        return 0

    upsert_result = upsert_tickers(result.records)
    print(f"supabase={upsert_result['status']}")
    print(f"supabase_upserted={upsert_result['upserted_count']}")

    if upsert_result["status"] != "success":
        print(f"supabase_message={upsert_result.get('message')}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
