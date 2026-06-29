import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_store.supabase_store import (  # noqa: E402
    fetch_news_events,
    update_news_event_classification,
)
from news_events.extraction_cache import (  # noqa: E402
    build_duplicate_classification_update,
    build_extraction_update,
    find_cached_duplicate_classification,
    should_skip_event,
)
from news_events.normalization import classify_source_quality  # noqa: E402


def parse_tickers(value: str | None) -> list[str | None]:
    if not value:
        return [None]

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify cached news_events without reprocessing existing rows.",
    )
    parser.add_argument("--tickers", help="Comma-separated tickers. Omit for all.")
    parser.add_argument("--mode", choices=["rule_based", "llm"], default="rule_based")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--only-unclassified",
        action="store_true",
        default=True,
        help="Only classify rows without cached extractor metadata. Default: true.",
    )
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="Force reclassification even when cached metadata exists.",
    )
    parser.add_argument("--skip-supabase", action="store_true")
    args = parser.parse_args()

    total_events = 0
    updated = 0
    skipped = 0
    duplicate_reused = 0

    for ticker in parse_tickers(args.tickers):
        events = fetch_news_events(ticker=ticker, limit=args.limit)
        total_events += len(events)
        print(f"ticker={ticker or 'ALL'} events={len(events)}")

        for event in events:
            if should_skip_event(
                event,
                only_unclassified=args.only_unclassified,
                reclassify=args.reclassify,
            ):
                skipped += 1
                continue

            source_quality = classify_source_quality(
                source=event.get("source") or "",
                source_type=event.get("source_type") or "",
            )
            cached_duplicate = None

            if not args.reclassify:
                cached_duplicate = find_cached_duplicate_classification(
                    event=event,
                    events=events,
                )

            if cached_duplicate:
                classification_update = build_duplicate_classification_update(
                    event=event,
                    cached_event=cached_duplicate,
                )
                duplicate_reused += 1
            else:
                classification_update = build_extraction_update(
                    event=event,
                    mode=args.mode,
                )

            if args.skip_supabase:
                updated += 1
                continue

            result = update_news_event_classification(
                event_id=event["id"],
                sentiment=classification_update["sentiment"],
                topic=classification_update["topic"],
                importance=classification_update["importance"],
                source_quality=source_quality,
                ticker_relevance=classification_update.get("ticker_relevance"),
                llm_summary=classification_update.get("llm_summary"),
                extractor_mode=classification_update.get("extractor_mode"),
                extractor_provider=classification_update.get("extractor_provider"),
                extractor_model=classification_update.get("extractor_model"),
                extracted_at=classification_update.get("extracted_at"),
                extraction_status=classification_update.get("extraction_status"),
                extraction_error=classification_update.get("extraction_error"),
                escalation_enabled=classification_update.get("escalation_enabled"),
                escalated=classification_update.get("escalated"),
                escalation_model=classification_update.get("escalation_model"),
                escalation_reason=classification_update.get("escalation_reason"),
                escalation_status=classification_update.get("escalation_status"),
                escalation_error=classification_update.get("escalation_error"),
            )
            if result["status"] != "success":
                print(f"event_id={event['id']} status={result['status']} message={result.get('message')}")
                return 1
            updated += 1

    print(f"events={total_events}")
    print(f"updated={updated}")
    print(f"skipped={skipped}")
    print(f"duplicate_reused={duplicate_reused}")
    print(f"mode={args.mode}")
    print("escalation=env")
    print(f"supabase={'skipped' if args.skip_supabase else 'success'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
