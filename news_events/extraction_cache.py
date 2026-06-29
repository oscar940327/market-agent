from datetime import UTC, datetime

from news_events.extractor import (
    classify_news_event_with_optional_llm,
    get_news_escalation_client_from_env,
    get_news_escalation_enabled,
    get_news_escalation_model,
)


CLASSIFIED_STATUSES = {"success", "fallback_rule_based", "skipped_duplicate"}


def is_news_event_classified(event: dict) -> bool:
    if event.get("extraction_status") not in CLASSIFIED_STATUSES:
        return False

    return all(
        event.get(field)
        for field in ["sentiment", "topic", "importance", "ticker_relevance"]
    )


def find_cached_duplicate_classification(
    event: dict,
    events: list[dict],
) -> dict | None:
    duplicate_group_id = event.get("duplicate_group_id")

    if not duplicate_group_id:
        return None

    for candidate in events:
        if candidate.get("id") == event.get("id"):
            continue

        if candidate.get("duplicate_group_id") != duplicate_group_id:
            continue

        if is_news_event_classified(candidate):
            return candidate

    return None


def build_duplicate_classification_update(event: dict, cached_event: dict) -> dict:
    return {
        "sentiment": cached_event["sentiment"],
        "topic": cached_event["topic"],
        "importance": cached_event["importance"],
        "ticker_relevance": cached_event.get("ticker_relevance"),
        "llm_summary": cached_event.get("llm_summary"),
        "extractor_mode": cached_event.get("extractor_mode"),
        "extractor_provider": cached_event.get("extractor_provider"),
        "extractor_model": cached_event.get("extractor_model"),
        "extracted_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "extraction_status": "skipped_duplicate",
        "extraction_error": None,
        "escalation_enabled": cached_event.get("escalation_enabled", False),
        "escalated": False,
        "escalation_model": cached_event.get("escalation_model"),
        "escalation_reason": "duplicate_group_reused",
        "escalation_status": "not_needed",
        "escalation_error": None,
    }


def build_extraction_update(
    *,
    event: dict,
    mode: str,
    llm_client=None,
    escalation_enabled: bool | None = None,
    escalation_client=None,
    escalation_model: str | None = None,
) -> dict:
    classification = classify_news_event_with_optional_llm(
        ticker=event.get("ticker") or "",
        title=event.get("title") or "",
        content_snippet=event.get("content_snippet"),
        mode=mode,
        llm_client=llm_client,
    )
    extractor = classification["extractor"]
    mode_used = extractor["mode_used"]
    fallback_used = bool(extractor.get("fallback_used"))

    if fallback_used and extractor.get("requested_mode") == "llm":
        extraction_status = "fallback_rule_based"
    else:
        extraction_status = "success"

    update = {
        "sentiment": classification["sentiment"],
        "topic": classification["topic"],
        "importance": classification["importance"],
        "ticker_relevance": classification.get("ticker_relevance", "unknown"),
        "llm_summary": classification.get("summary"),
        "extractor_mode": mode_used,
        "extractor_provider": extractor.get("provider"),
        "extractor_model": extractor.get("model"),
        "extracted_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "extraction_status": extraction_status,
        "extraction_error": extractor.get("message"),
        "escalation_enabled": resolve_escalation_enabled(escalation_enabled),
        "escalated": False,
        "escalation_model": None,
        "escalation_reason": None,
        "escalation_status": "not_applicable",
        "escalation_error": None,
    }

    return maybe_apply_escalation(
        event=event,
        update=update,
        escalation_client=escalation_client,
        escalation_model=escalation_model,
    )


def resolve_escalation_enabled(value: bool | None) -> bool:
    if value is None:
        return get_news_escalation_enabled()

    return bool(value)


def maybe_apply_escalation(
    *,
    event: dict,
    update: dict,
    escalation_client=None,
    escalation_model: str | None = None,
) -> dict:
    if not update["escalation_enabled"]:
        update["escalation_status"] = "not_applicable"
        return update

    should_escalate, reason = should_escalate_news_event(event=event, update=update)
    update["escalation_reason"] = reason

    if not should_escalate:
        update["escalation_status"] = "not_needed"
        return update

    model = escalation_model or get_news_escalation_model()
    client = escalation_client or get_news_escalation_client_from_env()
    update["escalation_model"] = model

    if client is None:
        update["escalation_status"] = "failed"
        update["escalation_error"] = "未設定 escalation LLM client，保留原分類結果。"
        return update

    try:
        escalated = classify_news_event_with_optional_llm(
            ticker=event.get("ticker") or "",
            title=event.get("title") or "",
            content_snippet=event.get("content_snippet"),
            mode="llm",
            llm_client=client,
        )
    except Exception as error:
        update["escalation_status"] = "failed"
        update["escalation_error"] = str(error)
        return update

    extractor = escalated["extractor"]

    if extractor.get("mode_used") != "llm" or extractor.get("fallback_used"):
        update["escalation_status"] = "failed"
        update["escalation_error"] = extractor.get(
            "message",
            "Escalation model did not return a usable LLM result.",
        )
        return update

    update.update(
        {
            "sentiment": escalated["sentiment"],
            "topic": escalated["topic"],
            "importance": escalated["importance"],
            "ticker_relevance": escalated.get("ticker_relevance", "unknown"),
            "llm_summary": escalated.get("summary"),
            "escalated": True,
            "escalation_model": getattr(client, "model", model),
            "escalation_status": "success",
            "escalation_error": None,
        }
    )

    return update


def should_escalate_news_event(*, event: dict, update: dict) -> tuple[bool, str]:
    ticker_relevance = update.get("ticker_relevance") or "unknown"
    importance = update.get("importance") or "unknown"
    topic = update.get("topic") or "general"
    sentiment = update.get("sentiment") or "unknown"
    source_quality = event.get("source_quality") or "unknown"

    if ticker_relevance == "low":
        return False, "ticker_relevance_low"

    if importance == "low":
        return False, "importance_low"

    if topic == "general" and sentiment == "neutral":
        return False, "general_neutral_news"

    if source_quality in {"low", "unknown"} and importance != "high":
        return False, "low_quality_not_high_importance"

    unclear = (
        sentiment == "unknown"
        or topic in {"general", "unknown"}
        or importance == "unknown"
        or ticker_relevance == "unknown"
    )

    if topic == "risk_event":
        return True, "risk_event"

    if importance == "high" and unclear:
        return True, "high_importance_unclear"

    if source_quality == "high" and unclear:
        return True, "high_quality_unclear"

    return False, "clear_or_low_impact"


def should_skip_event(
    event: dict,
    *,
    only_unclassified: bool = True,
    reclassify: bool = False,
) -> bool:
    if reclassify:
        return False

    if only_unclassified and is_news_event_classified(event):
        return True

    return False
