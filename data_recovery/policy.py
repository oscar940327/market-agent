from __future__ import annotations

from typing import Any


STATUS_PRIORITY = {
    "fresh": 0,
    "success": 0,
    "warning": 1,
    "stale": 2,
    "missing": 3,
    "failed": 4,
    "unavailable": 4,
}

SOURCE_POLICIES = {
    "daily_prices": {
        "action_id": "run_prices_pipeline",
        "command": "python scripts/run_daily_pipeline.py --only prices --tickers {ticker}",
        "affects": "technical_analysis",
        "safe_auto_recovery_candidate": True,
    },
    "technical_features": {
        "action_id": "recompute_technical_features",
        "command": "python scripts/compute_technical_features.py --tickers {ticker}",
        "affects": "technical_analysis",
        "safe_auto_recovery_candidate": True,
    },
    "market_regimes": {
        "action_id": "recompute_market_regime",
        "command": "python scripts/compute_market_regime.py",
        "affects": "market_context",
        "safe_auto_recovery_candidate": True,
    },
    "news_events": {
        "action_id": "run_news_pipeline",
        "command": "python scripts/run_daily_pipeline.py --only news --tickers {ticker}",
        "affects": "news_analysis",
        "safe_auto_recovery_candidate": True,
    },
    "fundamental_snapshots": {
        "action_id": "run_fundamentals_pipeline",
        "command": "python scripts/run_daily_pipeline.py --only fundamentals --tickers {ticker}",
        "affects": "fundamental_analysis",
        "safe_auto_recovery_candidate": True,
    },
    "ml_predictions": {
        "action_id": "run_daily_ml_predictions",
        "command": "python scripts/build_daily_ml_predictions.py --tickers {ticker}",
        "affects": "ml_reference",
        "safe_auto_recovery_candidate": True,
    },
    "ml_training_data": {
        "action_id": "rebuild_ml_training_dataset",
        "command": "python scripts/build_ml_training_dataset.py",
        "affects": "future_model_training",
        "safe_auto_recovery_candidate": False,
    },
    "pipeline_last_run": {
        "action_id": "inspect_pipeline_run",
        "command": None,
        "affects": "system_maintenance",
        "safe_auto_recovery_candidate": False,
    },
}


def build_data_recovery_report(
    *,
    freshness: dict | None,
    ticker: str,
    fundamentals: dict | None = None,
    ml_research: dict | None = None,
    ml_prediction: dict | None = None,
    include_news: bool = True,
    include_fundamentals: bool = True,
    include_technicals: bool = True,
    include_ml: bool = True,
) -> dict:
    freshness = freshness or {}
    ticker = ticker.upper()
    requested_sources = {
        "daily_prices": include_technicals,
        "technical_features": include_technicals,
        "market_regimes": include_technicals or include_ml,
        "news_events": include_news,
        "fundamental_snapshots": include_fundamentals,
        "ml_predictions": include_ml,
        "ml_training_data": False,
        "pipeline_last_run": False,
    }

    findings = []
    scoped_sources = None
    if freshness.get("scope_mode"):
        scoped_sources = {
            item.get("source") for item in freshness.get("warnings") or []
        }
    for source in SOURCE_POLICIES:
        if source == "ml_predictions":
            continue
        if scoped_sources is not None and source not in scoped_sources:
            continue
        section = freshness.get(source)
        if not isinstance(section, dict):
            continue
        status = normalize_status(section.get("status"))
        if status in {"fresh", "success"}:
            continue
        findings.append(
            build_finding(
                source=source,
                status=status,
                reason=section.get("reason", "unknown"),
                message=section.get("message", "Data is not ready."),
                ticker=ticker,
                affects_current_report=bool(requested_sources[source]),
                metadata_source=section.get("metadata_source"),
            )
        )

    fundamental_finding = build_fundamental_status_finding(
        fundamentals=fundamentals,
        ticker=ticker,
        enabled=include_fundamentals,
        existing_sources={item["source"] for item in findings},
    )
    if fundamental_finding:
        findings.append(fundamental_finding)

    ml_finding = build_ml_prediction_finding(
        ml_research=ml_research,
        ml_prediction=ml_prediction,
        ticker=ticker,
        enabled=include_ml,
    )
    if ml_finding:
        findings.append(ml_finding)

    findings.sort(
        key=lambda item: (
            not item["affects_current_report"],
            -STATUS_PRIORITY.get(item["status"], 0),
            item["source"],
        )
    )
    current_findings = [item for item in findings if item["affects_current_report"]]
    maintenance_findings = [item for item in findings if not item["affects_current_report"]]
    report_impact = classify_report_impact(current_findings)
    return {
        "recovery_version": "data_recovery_v1",
        "status": "healthy" if not findings else "action_recommended",
        "report_impact": report_impact,
        "current_report_usable": report_impact != "insufficient_data",
        "finding_count": len(findings),
        "current_report_finding_count": len(current_findings),
        "maintenance_finding_count": len(maintenance_findings),
        "email_alert_eligible": any(is_alertable(item) for item in findings),
        "automatic_recovery_executed": False,
        "automatic_recovery_policy": "advisory_only",
        "findings": findings,
        "summary": build_summary(findings, report_impact),
    }


def build_finding(
    *,
    source: str,
    status: str,
    reason: str,
    message: str,
    ticker: str,
    affects_current_report: bool,
    metadata_source: str | None = None,
) -> dict:
    policy = SOURCE_POLICIES[source]
    command = policy["command"]
    if command:
        command = command.format(ticker=ticker)
    return {
        "source": source,
        "status": status,
        "severity": classify_severity(status, affects_current_report),
        "reason": reason,
        "message": message,
        "affects_current_report": affects_current_report,
        "affected_output": policy["affects"],
        "recommended_action": {
            "id": policy["action_id"],
            "command": command,
            "safe_auto_recovery_candidate": policy["safe_auto_recovery_candidate"],
            "requires_user_approval": True,
        },
        "metadata_source": metadata_source,
    }


def build_fundamental_status_finding(
    *,
    fundamentals: dict | None,
    ticker: str,
    enabled: bool,
    existing_sources: set[str],
) -> dict | None:
    if (
        not enabled
        or fundamentals is None
        or "fundamental_snapshots" in existing_sources
    ):
        return None
    status = normalize_status((fundamentals or {}).get("status"))
    if status in {"success", "fresh"}:
        return None
    return build_finding(
        source="fundamental_snapshots",
        status="missing" if status == "unknown" else status,
        reason="fundamental_analysis_unavailable",
        message=(fundamentals or {}).get("message")
        or "基本面資料無法用於本次研究。",
        ticker=ticker,
        affects_current_report=True,
    )


def build_ml_prediction_finding(
    *,
    ml_research: dict | None,
    ml_prediction: dict | None,
    ticker: str,
    enabled: bool,
) -> dict | None:
    if not enabled:
        return None
    ml_research = ml_research or {}
    ml_prediction = ml_prediction or {}
    source = ml_research.get("source") or {}
    source_type = source.get("type")
    freshness = normalize_status(
        source.get("prediction_freshness")
        or ml_prediction.get("prediction_freshness")
    )
    status = normalize_status(ml_research.get("status"))
    if source_type == "saved_daily_prediction" and freshness in {"fresh", "success"}:
        return None
    if source_type == "runtime_fallback":
        recovery_status = "warning"
        reason = source.get("reason") or "saved_prediction_not_usable"
        message = "Saved ML prediction 無法使用，本次改用 runtime fallback。"
    elif status in {"missing", "failed", "unavailable"}:
        recovery_status = status
        reason = "ml_reference_unavailable"
        message = "ML prediction 無法用於本次研究。"
    elif freshness not in {"fresh", "success", "unknown"}:
        recovery_status = freshness
        reason = "saved_prediction_not_fresh"
        message = f"Saved ML prediction freshness 為 {freshness}。"
    else:
        return None
    return build_finding(
        source="ml_predictions",
        status=recovery_status,
        reason=reason,
        message=message,
        ticker=ticker,
        affects_current_report=True,
    )


def normalize_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    aliases = {"ready": "fresh", "partial_success": "warning", "skipped": "success"}
    return aliases.get(status, status)


def classify_severity(status: str, affects_current_report: bool) -> str:
    if affects_current_report and status in {"missing", "failed", "unavailable"}:
        return "high"
    if affects_current_report or status in {"stale", "missing", "failed"}:
        return "medium"
    return "low"


def classify_report_impact(findings: list[dict]) -> str:
    if any(
        item["source"] in {"daily_prices", "technical_features"}
        and item["status"] in {"missing", "failed", "unavailable"}
        for item in findings
    ):
        return "insufficient_data"
    if findings:
        return "usable_with_caution"
    return "none"


def is_alertable(finding: dict) -> bool:
    return finding["affects_current_report"] or finding["status"] in {
        "stale",
        "missing",
        "failed",
        "unavailable",
    }


def build_summary(findings: list[dict], report_impact: str) -> str:
    if not findings:
        return "目前沒有需要修復的資料缺口。"
    current_count = sum(item["affects_current_report"] for item in findings)
    maintenance_count = len(findings) - current_count
    return (
        f"找到 {len(findings)} 個資料或維護問題；{current_count} 個會影響本次報告，"
        f"{maintenance_count} 個只影響系統維護。報告影響為 {report_impact}。"
    )
