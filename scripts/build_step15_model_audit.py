import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_model_improvement import (  # noqa: E402
    build_baseline_audit_report,
    build_baseline_audit_summary_markdown,
    build_feature_label_diagnostics_report,
    build_feature_label_diagnostics_summary_markdown,
    build_target_metric_spec_report,
    build_target_metric_spec_summary_markdown,
)


DEFAULT_MODEL_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "model_reports"
DEFAULT_RETURN_REPORT_DIR = PROJECT_ROOT / "data" / "ml" / "return_model_reports"
DEFAULT_MONITORING_DIR = PROJECT_ROOT / "data" / "ml" / "monitoring"
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1_metadata.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Step 15 target spec and baseline audit reports.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_MODEL_REPORT_DIR))
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    parser.add_argument(
        "--skip-dataset-diagnostics",
        action="store_true",
        help="Only build target spec and baseline audit reports.",
    )
    parser.add_argument(
        "--baseline-metrics-path",
        default=str(DEFAULT_MODEL_REPORT_DIR / "baseline_metrics_v1.json"),
    )
    parser.add_argument(
        "--return-model-metrics-path",
        default=str(DEFAULT_RETURN_REPORT_DIR / "return_model_metrics_v1.json"),
    )
    parser.add_argument(
        "--monitoring-metrics-path",
        default=str(DEFAULT_MONITORING_DIR / "ml_monitoring_metrics_v1.json"),
    )
    parser.add_argument(
        "--calibration-path",
        default=str(DEFAULT_MONITORING_DIR / "ml_calibration_report_v1.json"),
    )
    parser.add_argument(
        "--health-path",
        default=str(DEFAULT_MONITORING_DIR / "ml_health_report_v1.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_spec = build_target_metric_spec_report()
    audit = build_baseline_audit_report(
        baseline_metrics=load_optional_json(args.baseline_metrics_path),
        return_model_metrics=load_optional_json(args.return_model_metrics_path),
        monitoring_metrics=load_optional_json(args.monitoring_metrics_path),
        calibration_report=load_optional_json(args.calibration_path),
        health_report=load_optional_json(args.health_path),
    )
    diagnostics = None
    if not args.skip_dataset_diagnostics:
        dataset_path = Path(args.dataset_path)
        if dataset_path.exists():
            diagnostics = build_feature_label_diagnostics_report(
                pd.read_csv(dataset_path),
                metadata=load_optional_json(args.metadata_path),
            )

    output_paths = write_reports(
        target_spec=target_spec,
        audit=audit,
        diagnostics=diagnostics,
        output_dir=output_dir,
    )
    print(f"target_spec_json={output_paths['target_spec_json']}")
    print(f"target_spec_markdown={output_paths['target_spec_markdown']}")
    print(f"audit_json={output_paths['audit_json']}")
    print(f"audit_markdown={output_paths['audit_markdown']}")
    if output_paths.get("diagnostics_json"):
        print(f"diagnostics_json={output_paths['diagnostics_json']}")
        print(f"diagnostics_markdown={output_paths['diagnostics_markdown']}")
    print(f"findings={audit['finding_summary']['total']}")
    print(f"critical={audit['finding_summary']['critical']}")
    for action in audit["next_actions"]:
        print(f"next_action={action}")
    if diagnostics:
        print(f"diagnostic_warnings={len(diagnostics['warnings'])}")
        for action in diagnostics["next_actions"]:
            print(f"diagnostic_next_action={action}")
    return 0


def write_reports(
    *,
    target_spec: dict,
    audit: dict,
    diagnostics: dict | None,
    output_dir: Path,
) -> dict[str, str]:
    paths = {
        "target_spec_json": output_dir / "step15_target_metric_spec_v1.json",
        "target_spec_markdown": output_dir / "step15_target_metric_spec_v1.md",
        "audit_json": output_dir / "step15_baseline_audit_v1.json",
        "audit_markdown": output_dir / "step15_baseline_audit_v1.md",
    }
    paths["target_spec_json"].write_text(
        json.dumps(target_spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["target_spec_markdown"].write_text(
        build_target_metric_spec_summary_markdown(target_spec),
        encoding="utf-8",
    )
    paths["audit_json"].write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["audit_markdown"].write_text(
        build_baseline_audit_summary_markdown(audit),
        encoding="utf-8",
    )
    if diagnostics is not None:
        paths["diagnostics_json"] = output_dir / "step15_feature_label_diagnostics_v1.json"
        paths["diagnostics_markdown"] = output_dir / "step15_feature_label_diagnostics_v1.md"
        paths["diagnostics_json"].write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["diagnostics_markdown"].write_text(
            build_feature_label_diagnostics_summary_markdown(diagnostics),
            encoding="utf-8",
        )
    return {key: str(path) for key, path in paths.items()}


def load_optional_json(path: str | None) -> dict | None:
    if not path:
        return None
    report_path = Path(path)
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
