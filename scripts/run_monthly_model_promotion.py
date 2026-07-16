import argparse
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts import load_alert_email_config, send_alert_email  # noqa: E402
from daily_ml_predictions import build_ml_model_run_row  # noqa: E402
from data_store import (  # noqa: E402
    fetch_active_shadow_model,
    fetch_ml_prediction_outcomes_for_metrics,
    insert_ml_model_run,
    upsert_ml_model_registry,
    upsert_ml_predictions,
    upsert_ml_promotion_review,
)
from ml_versions import CLASSIFICATION_MODEL_VERSION, DATASET_VERSION, FEATURE_VERSION  # noqa: E402
from model_promotion import (  # noqa: E402
    build_monthly_promotion_review,
    build_promotion_summary_markdown,
    build_shadow_prediction_records,
    train_shadow_candidate_models,
)


DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "ml" / "training_dataset_v1.csv"
DEFAULT_STEP28_PATH = (
    PROJECT_ROOT / "data" / "ml" / "model_reports" / "step28_model_quality_upgrade_v1.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "ml" / "promotion"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run monthly candidate review and controlled shadow validation."
    )
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--step28-path", default=str(DEFAULT_STEP28_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--production-model-version", default=CLASSIFICATION_MODEL_VERSION)
    parser.add_argument("--universe", default="QQQ100")
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dry-run-email", action="store_true")
    parser.add_argument("--skip-shadow-predictions", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generated = datetime.now(UTC)
    step28_report = load_json(args.step28_path)
    if not step28_report:
        raise FileNotFoundError(f"Step 28 report not found: {args.step28_path}")

    active_shadow = None
    production_outcomes = []
    shadow_outcomes = []
    if not args.dry_run:
        active_shadow = fetch_active_shadow_model()
        production_outcomes = fetch_ml_prediction_outcomes_for_metrics(
            universe=args.universe,
            model_version=args.production_model_version,
            days=0,
            limit=50_000,
        )
        if active_shadow:
            shadow_outcomes = fetch_ml_prediction_outcomes_for_metrics(
                universe=args.universe,
                model_version=active_shadow["model_version"],
                days=0,
                limit=50_000,
            )

    report = build_monthly_promotion_review(
        step28_report=step28_report,
        production_model_version=args.production_model_version,
        active_shadow=active_shadow,
        production_outcomes=production_outcomes,
        shadow_outcomes=shadow_outcomes,
        generated_at=generated,
    )

    shadow_result = {"status": "not_started", "prediction_count": 0}
    if report["recommendation"] == "start_shadow" and not args.skip_shadow_predictions:
        shadow_result = start_shadow_cohort(
            dataset_path=Path(args.dataset_path),
            step28_report=step28_report,
            candidate_version=report["candidate_model_version"],
            universe=args.universe,
            provider=args.provider,
            generated=generated,
            dry_run=args.dry_run,
        )
        if shadow_result["status"] not in {"success", "dry_run"}:
            report["recommendation"] = "unable_to_decide"
            report["recommendation_label"] = "目前無法判斷是否更換"
            report["next_action"] = "Shadow prediction 建立失敗，請檢查訓練或 Supabase 寫入錯誤。"
            report["summary"] = report["next_action"]
            report["checks"].append(
                {
                    "name": "shadow_cohort_creation",
                    "status": "unable",
                    "message": shadow_result.get("message") or shadow_result.get("reason"),
                    "details": {},
                }
            )
    report["shadow_cohort"] = shadow_result

    if active_shadow and not args.dry_run:
        lifecycle_result = update_existing_shadow_status(active_shadow, report)
        if lifecycle_result["status"] != "success":
            print("supabase=error")
            print(f"message={lifecycle_result.get('message')}")
            return 1

    paths = write_reports(report, output_dir=Path(args.output_dir))
    storage_result = {"status": "skipped"}
    if not args.dry_run:
        storage_result = upsert_ml_promotion_review(build_review_row(report))
        if storage_result["status"] != "success":
            print(f"supabase=error")
            print(f"message={storage_result.get('message')}")
            return 1

    email_result = None
    if args.send_email:
        alert = build_promotion_email(report, output_paths=paths)
        if args.dry_run_email or args.dry_run:
            email_result = {"status": "dry_run", "alert": alert}
        else:
            email_result = send_alert_email(alert, config=load_alert_email_config())

    print(f"recommendation={report['recommendation']}")
    print(f"recommendation_label={report['recommendation_label']}")
    print(f"candidate={report.get('candidate_model_version') or 'none'}")
    print(f"shadow_outcomes={report['shadow_outcome_count']}")
    print(f"shadow_predictions={shadow_result.get('prediction_count', 0)}")
    print(f"supabase={storage_result['status']}")
    print(f"json_path={paths['json_path']}")
    print(f"markdown_path={paths['markdown_path']}")
    if email_result:
        print(f"email={email_result['status']}")
    return 0


def start_shadow_cohort(
    *,
    dataset_path: Path,
    step28_report: dict,
    candidate_version: str,
    universe: str,
    provider: str,
    generated: datetime,
    dry_run: bool,
) -> dict:
    dataset = pd.read_csv(dataset_path)
    bundle = train_shadow_candidate_models(
        dataset,
        step28_report=step28_report,
        candidate_version=candidate_version,
    )
    if bundle["status"] != "success":
        return {
            "status": "failed",
            "reason": bundle.get("reason"),
            "message": f"Candidate training incomplete: {bundle.get('missing_targets')}",
            "prediction_count": 0,
        }

    data_as_of = str(dataset["date"].max())[:10]
    run_row = build_ml_model_run_row(
        data_as_of=data_as_of,
        model_version=candidate_version,
        feature_version=FEATURE_VERSION,
        dataset_version=DATASET_VERSION,
        universe=universe,
        provider=provider,
        started_at=generated,
        config={
            "prediction_role": "shadow",
            "research_report_visible": False,
            "trained_targets": bundle["trained_targets"],
        },
    )
    run_row.update(
        {
            "run_name": f"monthly_shadow_{candidate_version}",
            "run_type": "experiment",
            "model_type": "experiment",
        }
    )
    if dry_run:
        run_id = "00000000-0000-0000-0000-000000000000"
    else:
        run_result = insert_ml_model_run(run_row)
        if run_result["status"] != "success":
            return {
                "status": "failed",
                "message": run_result.get("message"),
                "prediction_count": 0,
            }
        run_id = run_result["row"]["id"]

    records = build_shadow_prediction_records(
        dataset,
        candidate_bundle=bundle,
        model_run_id=run_id,
        universe=universe,
        provider=provider,
    )
    if dry_run:
        return {
            "status": "dry_run",
            "model_run_id": run_id,
            "prediction_count": len(records),
            "trained_targets": bundle["trained_targets"],
        }
    prediction_result = upsert_ml_predictions(records)
    if prediction_result["status"] != "success":
        return {
            "status": "failed",
            "message": prediction_result.get("message"),
            "prediction_count": 0,
        }
    registry_result = upsert_ml_model_registry(
        {
            "model_version": candidate_version,
            "model_role": "shadow",
            "lifecycle_status": "shadow_active",
            "source_report_version": step28_report.get("report_version"),
            "dataset_version": DATASET_VERSION,
            "feature_version": FEATURE_VERSION,
            "data_as_of": data_as_of,
            "started_at": generated.replace(microsecond=0).isoformat(),
            "metadata": {
                "prediction_count": len(records),
                "trained_targets": bundle["trained_targets"],
                "research_report_visible": False,
            },
        }
    )
    if registry_result["status"] != "success":
        return {
            "status": "failed",
            "message": registry_result.get("message"),
            "prediction_count": len(records),
        }
    return {
        "status": "success",
        "model_run_id": run_id,
        "prediction_count": len(records),
        "trained_targets": bundle["trained_targets"],
    }


def update_existing_shadow_status(active_shadow: dict, report: dict) -> dict:
    status = {
        "continue_shadow": "shadow_observing",
        "promote_candidate": "promotion_recommended",
        "keep_production": "rejected",
        "unable_to_decide": "shadow_observing",
    }.get(report["recommendation"])
    if not status:
        return {"status": "skipped", "message": "No lifecycle update needed."}
    row = {**active_shadow, "lifecycle_status": status}
    row.pop("id", None)
    row["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    if status in {"promotion_recommended", "rejected"}:
        row["completed_at"] = row["updated_at"]
    return upsert_ml_model_registry(row)


def build_review_row(report: dict) -> dict:
    return {
        "review_version": report["review_version"],
        "review_month": report["review_month"],
        "production_model_version": report["production_model_version"],
        "candidate_model_version": report.get("candidate_model_version") or "none",
        "recommendation": report["recommendation"],
        "recommendation_label": report["recommendation_label"],
        "shadow_outcome_count": report["shadow_outcome_count"],
        "report": report,
    }


def write_reports(report: dict, *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = report["review_month"][:7].replace("-", "")
    json_path = output_dir / f"model_promotion_review_{suffix}.json"
    markdown_path = output_dir / f"model_promotion_review_{suffix}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(build_promotion_summary_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def build_promotion_email(report: dict, *, output_paths: dict[str, str]) -> dict:
    label = report["recommendation_label"]
    subject = f"[Market Agent] 每月模型評估：{label}"
    text = "\n".join(
        [
            "Market Agent 每月模型評估",
            "",
            f"明確建議：{label}",
            f"Production：{report['production_model_version']}",
            f"Candidate：{report.get('candidate_model_version') or 'none'}",
            f"Shadow outcomes：{report['shadow_outcome_count']}",
            f"下一步：{report['next_action']}",
            "",
            "系統不會自動替換正式模型。",
            f"Report：{output_paths['json_path']}",
        ]
    )
    rows = "".join(
        f"<tr><td>{html.escape(item['name'])}</td><td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(item['message'])}</td></tr>"
        for item in report["checks"]
    )
    body = f"""<!doctype html><html><body style="font-family:Arial;color:#2d2a26;background:#f7f3ec;padding:24px">
<div style="max-width:760px;margin:auto;background:#fffdf8;border:1px solid #ded6c8;border-radius:8px;padding:24px">
<h1 style="font-size:22px">Market Agent 每月模型評估</h1>
<p><strong>明確建議：{html.escape(label)}</strong></p>
<table style="border-collapse:collapse;width:100%"><tr><th align="left">Production</th><td>{html.escape(report['production_model_version'])}</td></tr>
<tr><th align="left">Candidate</th><td>{html.escape(report.get('candidate_model_version') or 'none')}</td></tr>
<tr><th align="left">Shadow outcomes</th><td>{report['shadow_outcome_count']}</td></tr></table>
<h2 style="font-size:16px">檢查結果</h2><table style="border-collapse:collapse;width:100%">{rows}</table>
<h2 style="font-size:16px">下一步</h2><p>{html.escape(report['next_action'])}</p>
<p><strong>系統不會自動替換正式模型。</strong></p>
</div></body></html>"""
    return {
        "should_send": True,
        "reason": "monthly_model_promotion_review",
        "subject": subject,
        "severity": "warning" if report["recommendation"] in {"keep_production", "unable_to_decide"} else "info",
        "pipeline": "monthly-model-promotion",
        "status": report["recommendation"],
        "summary": label,
        "warnings": [],
        "errors": [],
        "failed_steps": [],
        "log_path": output_paths["json_path"],
        "latest_log_path": output_paths["markdown_path"],
        "text": text,
        "html": body,
    }


def load_json(path: str | Path) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
