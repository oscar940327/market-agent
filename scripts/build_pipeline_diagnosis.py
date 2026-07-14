import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maintenance.diagnostics import (  # noqa: E402
    build_pipeline_diagnosis,
    load_json_sources,
    render_diagnosis_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a rule-based pipeline diagnosis report.")
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--status", default="unknown")
    parser.add_argument("--message")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--input-paths", default="")
    parser.add_argument("--run-url")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data" / "maintenance" / "diagnoses"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = [*args.input, *[part.strip() for part in args.input_paths.split(",") if part.strip()]]
    sources = load_json_sources(paths)
    diagnosis = build_pipeline_diagnosis(
        pipeline=args.pipeline,
        workflow_status=args.status,
        sources=sources,
        message=args.message,
        run_url=args.run_url or build_github_run_url(),
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(args.pipeline)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    json_path = output_dir / f"{slug}_{timestamp}.json"
    markdown_path = output_dir / f"{slug}_{timestamp}.md"
    latest_json = output_dir / f"{slug}_latest.json"
    latest_markdown = output_dir / f"{slug}_latest.md"
    json_text = json.dumps(diagnosis, ensure_ascii=False, indent=2)
    markdown_text = render_diagnosis_markdown(diagnosis)
    for path in (json_path, latest_json):
        path.write_text(json_text, encoding="utf-8")
    for path in (markdown_path, latest_markdown):
        path.write_text(markdown_text, encoding="utf-8")
    write_github_output(diagnosis, latest_json)
    print(f"diagnosis_status={diagnosis['status']}")
    print(f"diagnosis_severity={diagnosis['severity']}")
    print(f"diagnosis_issue={str(diagnosis['issue']['should_create']).lower()}")
    print(f"diagnosis_path={latest_json}")
    return 0


def safe_slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-")


def build_github_run_url() -> str | None:
    server = os.getenv("GITHUB_SERVER_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if not all((server, repository, run_id)):
        return None
    return f"{server}/{repository}/actions/runs/{run_id}"


def write_github_output(diagnosis: dict, path: Path) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"diagnosis_path={path.as_posix()}\n")
        output.write(f"should_create_issue={str(diagnosis['issue']['should_create']).lower()}\n")
        output.write(f"fingerprint={diagnosis['issue']['fingerprint']}\n")


if __name__ == "__main__":
    raise SystemExit(main())
