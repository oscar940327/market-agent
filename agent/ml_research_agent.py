from agent.agent_output import build_agent_output
from daily_ml_predictions import (
    build_runtime_fallback_source,
    build_unavailable_source,
    convert_saved_prediction_to_ml_research,
    is_saved_prediction_usable,
)
from data_store import fetch_latest_ml_prediction
from ml_research import build_single_stock_ml_research


def build_ml_research_for_single_stock(
    ticker: str,
    include_ml: bool = True,
    fetch_prediction=None,
    runtime_builder=None,
) -> tuple[dict, dict | None]:
    if not include_ml:
        return (
            {
                "status": "skipped",
                "usage_policy": "reference_only",
                "reason": "ml_disabled_for_internal_workflow",
                "summary": "ML reference was skipped for this internal workflow.",
                "source": {"type": "skipped", "reason": "include_ml_false"},
            },
            None,
        )

    fetch_prediction = fetch_prediction or safe_fetch_latest_ml_prediction
    runtime_builder = runtime_builder or build_single_stock_ml_research

    saved_prediction = fetch_prediction(ticker=ticker)
    if is_saved_prediction_usable(saved_prediction):
        return convert_saved_prediction_to_ml_research(saved_prediction), saved_prediction

    fallback_reason = build_saved_prediction_fallback_reason(saved_prediction)
    runtime_ml_research = runtime_builder(ticker=ticker)
    if runtime_ml_research.get("status") == "success":
        runtime_ml_research["source"] = build_runtime_fallback_source(
            reason=fallback_reason,
            saved_prediction=saved_prediction,
        )
    else:
        runtime_ml_research["source"] = build_unavailable_source(
            reason=fallback_reason,
            saved_prediction=saved_prediction,
        )
    return runtime_ml_research, saved_prediction


def safe_fetch_latest_ml_prediction(ticker: str) -> dict | None:
    try:
        return fetch_latest_ml_prediction(ticker=ticker)
    except Exception:
        return None


def build_saved_prediction_fallback_reason(saved_prediction: dict | None) -> str:
    if not saved_prediction:
        return "no_saved_daily_prediction"

    status = saved_prediction.get("prediction_status", "unknown")
    freshness = saved_prediction.get("prediction_freshness", "unknown")
    return f"saved_prediction_not_usable:{status}/{freshness}"


def build_ml_research_agent_output(ticker: str, ml_research: dict) -> dict:
    return build_agent_output(
        agent="ml_research",
        status=map_ml_research_status(ml_research),
        summary=ml_research.get("summary")
        or ml_research.get("message")
        or ml_research.get("reason", ""),
        payload=ml_research,
        warnings=build_ml_research_warnings(ml_research),
        metadata={
            "ticker": ticker,
            "source": (ml_research.get("source") or {}).get("type"),
        },
        fallback_used=(ml_research.get("source") or {}).get("type")
        == "runtime_fallback",
        legacy_fields=ml_research,
    )


def map_ml_research_status(ml_research: dict) -> str:
    status = ml_research.get("status", "unavailable")

    if status in {"success", "skipped", "unavailable", "failed"}:
        return status
    if status in {"not_ready", "stale", "missing_model"}:
        return "unavailable"

    return "partial_success"


def build_ml_research_warnings(ml_research: dict) -> list[str]:
    status = ml_research.get("status")
    warnings = []

    if status not in {None, "success"}:
        reason = ml_research.get("reason") or ml_research.get("message") or status
        warnings.append(str(reason))

    source = ml_research.get("source") or {}
    if source.get("type") in {"runtime_fallback", "unavailable"}:
        reason = source.get("reason")
        warnings.append(f"ml_source:{source.get('type')}:{reason}")

    return warnings
