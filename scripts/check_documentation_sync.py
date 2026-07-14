import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maintenance.documentation import check_documentation_sync  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether code changes include the matching documentation update.")
    parser.add_argument("--base-ref", help="Git base ref or commit used for the diff.")
    parser.add_argument("--path", action="append", default=[], help="Explicit changed path for tests or local checks.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    changed_paths = args.path or get_changed_paths(args.base_ref)
    findings = check_documentation_sync(changed_paths)
    print(f"changed_paths={len(changed_paths)}")
    print(f"documentation_findings={len(findings)}")
    for finding in findings:
        print(f"warning={finding['message']}")
        print(f"accepted_docs={','.join(finding['accepted_docs'])}")
    return 1 if findings else 0


def get_changed_paths(base_ref: str | None) -> list[str]:
    command = ["git", "diff", "--name-only"]
    if base_ref:
        command.append(f"{base_ref}...HEAD")
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to inspect changed files.")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
