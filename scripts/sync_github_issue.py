import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maintenance.github_issues import sync_diagnosis_issue  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or update a GitHub Issue for a pipeline diagnosis.")
    parser.add_argument("--diagnosis", required=True)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN", ""))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    diagnosis = json.loads(Path(args.diagnosis).read_text(encoding="utf-8"))
    if args.dry_run:
        result = {
            "status": "dry_run",
            "would_create": bool((diagnosis.get("issue") or {}).get("should_create")),
        }
    else:
        try:
            result = sync_diagnosis_issue(
                diagnosis,
                repository=args.repository,
                token=args.token,
            )
        except Exception as error:
            # Issue tracking must not hide or replace the original pipeline result.
            result = {"status": "failed", "reason": "github_api_error", "error": str(error)}
    print(f"issue_sync_status={result['status']}")
    if result.get("reason"):
        print(f"issue_sync_reason={result['reason']}")
    if result.get("issue_url"):
        print(f"issue_url={result['issue_url']}")
    if result.get("error"):
        print(f"issue_sync_error={result['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
