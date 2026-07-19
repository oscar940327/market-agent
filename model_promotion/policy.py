from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable


DEFAULT_PROMOTION_POLICY = {
    "minimum_shadow_outcomes_per_horizon": 100,
    "minimum_shadow_age_days": 45,
    "maximum_accuracy_regression": 0.01,
    "maximum_brier_regression": 0.01,
    "maximum_large_drop_recall_regression": 0.05,
    "maximum_large_drop_brier_regression": 0.01,
    "automatic_production_replacement": False,
}

RECOMMENDATION_LABELS = {
    "no_candidate": "本月沒有可進入驗證的候選模型",
    "keep_production": "不建議更換正式模型",
    "start_shadow": "建議候選模型進入並行觀察",
    "continue_shadow": "建議繼續並行觀察",
    "promote_candidate": "建議更換正式模型",
    "unable_to_decide": "目前無法判斷是否更換",
}


def build_monthly_promotion_review(
    *,
    step28_report: dict | None,
    production_model_version: str,
    active_shadow: dict | None = None,
    production_outcomes: list[dict] | None = None,
    shadow_outcomes: list[dict] | None = None,
    generated_at: datetime | None = None,
    policy: dict | None = None,
) -> dict:
    generated = generated_at or datetime.now(UTC)
    rules = {**DEFAULT_PROMOTION_POLICY, **(policy or {})}
    production_metrics = calculate_outcome_metrics(production_outcomes or [])
    shadow_metrics = calculate_outcome_metrics(shadow_outcomes or [])
    candidate_version = (active_shadow or {}).get("model_version")
    checks: list[dict] = []

    if active_shadow:
        candidate_targets = active_shadow_targets(active_shadow)
        recommendation, checks = review_active_shadow(
            active_shadow=active_shadow,
            production_metrics=production_metrics,
            shadow_metrics=shadow_metrics,
            generated_at=generated,
            policy=rules,
            candidate_targets=candidate_targets,
        )
    else:
        candidate_targets = passed_candidate_targets(step28_report)
        recommendation, checks = review_new_candidate(step28_report)
        candidate_version = candidate_version or infer_candidate_version(
            step28_report,
            generated=generated,
        )

    label = RECOMMENDATION_LABELS[recommendation]
    shadow_count = sum(
        item.get("sample_size", 0) for item in shadow_metrics.get("horizons", {}).values()
    )
    return {
        "review_version": "monthly_model_promotion_v1",
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "review_month": generated.date().replace(day=1).isoformat(),
        "production_model_version": production_model_version,
        "candidate_model_version": candidate_version,
        "candidate_targets": candidate_targets,
        "recommendation": recommendation,
        "recommendation_label": label,
        "automatic_replacement": False,
        "requires_user_confirmation": recommendation == "promote_candidate",
        "shadow_visibility": "monitoring_only",
        "research_report_affected": False,
        "production_metrics": production_metrics,
        "shadow_metrics": shadow_metrics,
        "shadow_outcome_count": shadow_count,
        "checks": checks,
        "policy": rules,
        "next_action": next_action(recommendation),
        "summary": build_summary(recommendation, checks),
    }


def review_new_candidate(step28_report: dict | None) -> tuple[str, list[dict]]:
    if not step28_report:
        return "no_candidate", [
            check("step28_report", "missing", "找不到本月候選模型評估報告。")
        ]
    promotion = step28_report.get("promotion") or {}
    status = promotion.get("status")
    if status in {"candidate_bundle_ready", "partial_candidate_ready"}:
        passed_targets = passed_candidate_targets(step28_report)
        return "start_shadow", [
            check(
                "walk_forward_policy",
                "pass",
                f"Step 28 通過的候選 targets：{', '.join(passed_targets)}。",
            )
        ]
    return "keep_production", [
        check(
            "walk_forward_policy",
            "reject",
            "候選模型尚未通過完整 walk-forward promotion policy。",
            details={
                "status": status or "unknown",
                "passed_targets": promotion.get("passed_targets") or [],
                "blocked_targets": promotion.get("blocked_targets") or [],
            },
        )
    ]


def review_active_shadow(
    *,
    active_shadow: dict,
    production_metrics: dict,
    shadow_metrics: dict,
    generated_at: datetime,
    policy: dict,
    candidate_targets: list[str],
) -> tuple[str, list[dict]]:
    checks: list[dict] = []
    age_days = shadow_age_days(active_shadow, generated_at)
    age_ready = age_days is not None and age_days >= policy["minimum_shadow_age_days"]
    checks.append(
        check(
            "shadow_age",
            "pass" if age_ready else "pending",
            f"Shadow 已觀察 {age_days if age_days is not None else 0} 天。",
            details={"minimum_days": policy["minimum_shadow_age_days"]},
        )
    )

    targets_ready = True
    for target in candidate_targets:
        horizon = target_horizon(target)
        horizon_metrics = shadow_metrics.get("horizons", {}).get(str(horizon), {})
        sample_key = "large_drop_sample_size" if target == "large_drop_20d" else "up_sample_size"
        sample_size = horizon_metrics.get(sample_key, 0)
        ready = sample_size >= policy["minimum_shadow_outcomes_per_horizon"]
        targets_ready &= ready
        checks.append(
            check(
                f"shadow_sample_{target}",
                "pass" if ready else "pending",
                f"{target} 已有 {sample_size} 筆成熟 shadow outcomes。",
                details={
                    "minimum": policy["minimum_shadow_outcomes_per_horizon"],
                    "horizon": horizon,
                },
            )
        )

    if not age_ready or not targets_ready:
        return "continue_shadow", checks

    comparisons = compare_shadow_to_production(
        production_metrics=production_metrics,
        shadow_metrics=shadow_metrics,
        policy=policy,
        candidate_targets=candidate_targets,
    )
    checks.extend(comparisons)
    if any(item["status"] == "unable" for item in comparisons):
        return "unable_to_decide", checks
    if any(item["status"] == "reject" for item in comparisons):
        return "keep_production", checks
    return "promote_candidate", checks


def compare_shadow_to_production(
    *,
    production_metrics: dict,
    shadow_metrics: dict,
    policy: dict,
    candidate_targets: list[str],
) -> list[dict]:
    checks = []
    up_horizons = sorted(
        {target_horizon(target) for target in candidate_targets if target.startswith("up_")}
    )
    for horizon in up_horizons:
        production = production_metrics.get("horizons", {}).get(str(horizon), {})
        shadow = shadow_metrics.get("horizons", {}).get(str(horizon), {})
        checks.extend(
            compare_metric(
                name=f"up_accuracy_{horizon}d",
                production=production.get("up_accuracy"),
                candidate=shadow.get("up_accuracy"),
                lower_is_better=False,
                tolerance=policy["maximum_accuracy_regression"],
            )
        )
        checks.extend(
            compare_metric(
                name=f"brier_score_{horizon}d",
                production=production.get("brier_score"),
                candidate=shadow.get("brier_score"),
                lower_is_better=True,
                tolerance=policy["maximum_brier_regression"],
            )
        )
    if "large_drop_20d" in candidate_targets:
        production_20 = production_metrics.get("horizons", {}).get("20", {})
        shadow_20 = shadow_metrics.get("horizons", {}).get("20", {})
        checks.extend(
            compare_metric(
                name="large_drop_recall_20d",
                production=production_20.get("large_drop_recall"),
                candidate=shadow_20.get("large_drop_recall"),
                lower_is_better=False,
                tolerance=policy["maximum_large_drop_recall_regression"],
            )
        )
        checks.extend(
            compare_metric(
                name="large_drop_brier_20d",
                production=production_20.get("large_drop_brier_score"),
                candidate=shadow_20.get("large_drop_brier_score"),
                lower_is_better=True,
                tolerance=policy["maximum_large_drop_brier_regression"],
            )
        )
    return checks


def compare_metric(
    *, name: str, production, candidate, lower_is_better: bool, tolerance: float
) -> list[dict]:
    if production is None or candidate is None:
        return [check(name, "unable", "正式模型或 shadow 模型缺少可比較數字。")]
    if lower_is_better:
        passed = candidate <= production + tolerance
    else:
        passed = candidate >= production - tolerance
    return [
        check(
            name,
            "pass" if passed else "reject",
            f"production={production:.4f}, shadow={candidate:.4f}",
            details={"tolerance": tolerance, "lower_is_better": lower_is_better},
        )
    ]


def calculate_outcome_metrics(rows: Iterable[dict]) -> dict:
    grouped: dict[int, list[dict]] = {5: [], 10: [], 20: []}
    for row in rows:
        try:
            horizon = int(row.get("horizon_trading_days"))
        except (TypeError, ValueError):
            continue
        if horizon in grouped and row.get("outcome_status") == "computed":
            grouped[horizon].append(row)

    horizons = {}
    for horizon, items in grouped.items():
        probabilities = [
            (float(item["predicted_up_probability"]), bool(item["actual_up"]))
            for item in items
            if item.get("predicted_up_probability") is not None
            and item.get("actual_up") is not None
        ]
        up_correct = [item.get("up_prediction_correct") for item in items]
        up_correct = [bool(value) for value in up_correct if value is not None]
        large_drop_rows = [
            item for item in items if item.get("actual_max_drop_pct") is not None
        ]
        actual_large_drops = [
            item for item in large_drop_rows if float(item["actual_max_drop_pct"]) <= -0.08
        ]
        large_drop_probabilities = [
            (
                float(item["predicted_large_drop_risk"]),
                float(item["actual_max_drop_pct"]) <= -0.08,
            )
            for item in large_drop_rows
            if item.get("predicted_large_drop_risk") is not None
        ]
        recalled = [
            item for item in actual_large_drops
            if item.get("predicted_large_drop_risk") is not None
            and (
                item.get("large_drop_prediction_correct") is True
                if item.get("large_drop_prediction_correct") is not None
                else float(item["predicted_large_drop_risk"]) >= 0.5
            )
        ]
        horizons[str(horizon)] = {
            "sample_size": len(items),
            "up_sample_size": len(probabilities),
            "up_accuracy": mean(up_correct),
            "brier_score": mean([(probability - float(actual)) ** 2 for probability, actual in probabilities]),
            "large_drop_recall": (
                len(recalled) / len(actual_large_drops) if actual_large_drops else None
            ),
            "large_drop_sample_size": len(large_drop_probabilities),
            "large_drop_brier_score": mean(
                [
                    (probability - float(actual)) ** 2
                    for probability, actual in large_drop_probabilities
                ]
            ),
            "actual_large_drop_count": len(actual_large_drops),
        }
    return {"horizons": horizons}


def build_promotion_summary_markdown(report: dict) -> str:
    lines = [
        "# Monthly Model Promotion Review",
        "",
        f"- Recommendation: **{report['recommendation_label']}** (`{report['recommendation']}`)",
        f"- Production: `{report['production_model_version']}`",
        f"- Candidate: `{report.get('candidate_model_version') or 'none'}`",
        f"- Candidate targets: `{', '.join(report.get('candidate_targets') or []) or 'none'}`",
        f"- Shadow outcomes: `{report['shadow_outcome_count']}`",
        f"- Automatic replacement: `{report['automatic_replacement']}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(
        f"- `{item['status']}` {item['name']}: {item['message']}"
        for item in report["checks"]
    )
    lines.extend(["", "## Next Action", "", report["next_action"], ""])
    return "\n".join(lines)


def infer_candidate_version(report: dict | None, *, generated: datetime) -> str | None:
    promotion = (report or {}).get("promotion") or {}
    if promotion.get("status") not in {
        "candidate_bundle_ready",
        "partial_candidate_ready",
    }:
        return None
    return f"candidate_{generated:%Y%m}"


def passed_candidate_targets(report: dict | None) -> list[str]:
    promotion = (report or {}).get("promotion") or {}
    return sorted(str(target) for target in promotion.get("passed_targets") or [])


def active_shadow_targets(active_shadow: dict) -> list[str]:
    metadata = active_shadow.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            import json

            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}
    targets = metadata.get("trained_targets") if isinstance(metadata, dict) else None
    default_targets = ["up_5d", "up_10d", "up_20d", "large_drop_20d"]
    return sorted(str(target) for target in (targets or default_targets))


def target_horizon(target: str) -> int:
    if target.endswith("_5d"):
        return 5
    if target.endswith("_10d"):
        return 10
    return 20


def shadow_age_days(active_shadow: dict, generated_at: datetime) -> int | None:
    value = active_shadow.get("started_at") or active_shadow.get("created_at")
    if not value:
        return None
    try:
        started = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return max(0, (generated_at - started).days)


def check(name: str, status: str, message: str, *, details: dict | None = None) -> dict:
    return {"name": name, "status": status, "message": message, "details": details or {}}


def mean(values: list[float | bool]) -> float | None:
    return sum(float(value) for value in values) / len(values) if values else None


def next_action(recommendation: str) -> str:
    return {
        "no_candidate": "保留正式模型，等待下個月重新評估。",
        "keep_production": "保留正式模型，不啟動或停止目前候選模型。",
        "start_shadow": "將候選模型註冊為 shadow，開始累積真實 outcomes。",
        "continue_shadow": "維持正式模型，繼續累積 shadow outcomes。",
        "promote_candidate": "Email 明確建議更換；需由使用者確認後才能執行正式升級。",
        "unable_to_decide": "檢查缺失 outcomes 或 pipeline，再重新執行 promotion review。",
    }[recommendation]


def build_summary(recommendation: str, checks: list[dict]) -> str:
    blocked = [item["name"] for item in checks if item["status"] in {"reject", "unable"}]
    suffix = f" 未通過：{', '.join(blocked)}。" if blocked else ""
    return f"{RECOMMENDATION_LABELS[recommendation]}。{suffix}".strip()
