from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/parsed/aruodas_candidates_text_enriched.json")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_coordinate_queue.json")
DEFAULT_LIMIT = 12
QUEUE_VERSION = "aruodas-coordinate-queue-v1"


def _quality_adjustment(item: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Small post-text adjustment used only to prioritize manual coordinate work.

    This does not replace aruodas_candidate_score and is not an arbitrage or
    profitability score. It simply decides which surviving listings are most
    worth opening/saving next.
    """

    enrichment = item.get("text_enrichment") or {}
    adjustment = 0.0
    positives: list[str] = []
    concerns: list[str] = []

    equipment = enrichment.get("equipment_state")
    if equipment == "newly_fitted":
        adjustment += 2.0
        positives.append("newly_fitted")
    elif equipment == "fully_furnished":
        adjustment += 1.0
        positives.append("fully_furnished")

    parking = enrichment.get("parking")
    if parking is True:
        adjustment += 2.0
        positives.append("parking")
    elif parking in {"optional", "optional_paid", "possible"}:
        adjustment += 1.0
        positives.append("parking_possible")

    feature_weights = {
        "terrace": 1.5,
        "balcony": 1.0,
        "air_conditioning": 1.5,
        "dishwasher": 1.0,
        "dryer": 0.5,
        "high_ceilings": 1.0,
        "separate_entrance": 1.0,
        "multi_level": 0.5,
    }

    for field, weight in feature_weights.items():
        if enrichment.get(field) is True:
            adjustment += weight
            positives.append(field)

    # Semi-basement units can still be retained in the dataset, but they are
    # poor candidates for spending manual coordinate-enrichment time on.
    if enrichment.get("basement_or_semi_basement") is True:
        adjustment -= 15.0
        concerns.append("basement_or_semi_basement")

    conflicts = enrichment.get("search_index_conflicts") or []
    if conflicts:
        adjustment -= 3.0
        concerns.append("search_index_conflict")

    broker_fee = enrichment.get("broker_fee_eur")
    if broker_fee:
        adjustment -= 1.0
        concerns.append("broker_fee")

    if (enrichment.get("deposit_months") or 0) >= 2:
        adjustment -= 0.5
        concerns.append("two_plus_month_deposit")

    negative_signals = set(enrichment.get("negative_signals") or [])
    if "elevator_out_of_service" in negative_signals:
        adjustment -= 1.5
        concerns.append("elevator_out_of_service")

    return adjustment, positives, concerns


def coordinate_priority(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    base_score = float(item.get("aruodas_candidate_score") or 0.0)
    adjustment, positives, concerns = _quality_adjustment(item)

    result["coordinate_queue_score"] = round(base_score + adjustment, 1)
    result["coordinate_queue_adjustment"] = round(adjustment, 1)
    result["coordinate_queue_positives"] = positives
    result["coordinate_queue_concerns"] = concerns
    result["coordinate_queue_version"] = QUEUE_VERSION
    return result


def is_coordinate_candidate(item: dict[str, Any]) -> bool:
    if item.get("candidate_tier") not in {"HIGH", "PROMISING"}:
        return False
    if item.get("candidate_hard_reject"):
        return False
    if item.get("post_enrichment_status") != "SURVIVOR":
        return False
    if item.get("text_enrichment_status") != "enriched":
        return False
    if item.get("coordinates_found") is True:
        return False
    if item.get("latitude") is not None and item.get("longitude") is not None:
        return False
    return True


def build_coordinate_queue(
    items: list[dict[str, Any]],
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    eligible = [coordinate_priority(item) for item in items if is_coordinate_candidate(item)]
    eligible.sort(
        key=lambda item: (
            item["coordinate_queue_score"],
            item.get("aruodas_candidate_score") or 0,
            -(float(item.get("rent_eur") or 10_000)),
        ),
        reverse=True,
    )

    queue: list[dict[str, Any]] = []
    for item in eligible[:limit]:
        listing_id = item["listing_id"]
        queue.append(
            {
                "rank": len(queue) + 1,
                "listing_id": listing_id,
                "url": item.get("url"),
                "district": item.get("district"),
                "street": item.get("street"),
                "rooms": item.get("rooms"),
                "area_m2": item.get("area_m2"),
                "rent_eur": item.get("rent_eur"),
                "aruodas_candidate_score": item.get("aruodas_candidate_score"),
                "candidate_tier": item.get("candidate_tier"),
                "coordinate_queue_score": item["coordinate_queue_score"],
                "coordinate_queue_adjustment": item["coordinate_queue_adjustment"],
                "coordinate_queue_positives": item["coordinate_queue_positives"],
                "coordinate_queue_concerns": item["coordinate_queue_concerns"],
                "description_summary": (item.get("text_enrichment") or {}).get(
                    "description_summary"
                ),
                "save_as": f"data/raw/detail_{listing_id}.html",
                "coordinate_queue_version": QUEUE_VERSION,
            }
        )

    return queue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small manual detail-page queue for exact Aruodas coordinates."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Text-enriched candidate dataset not found: {args.input}")

    items = json.loads(args.input.read_text(encoding="utf-8"))
    eligible_count = sum(1 for item in items if is_coordinate_candidate(item))
    exact_count = sum(
        1
        for item in items
        if item.get("coordinates_found") is True
        or (item.get("latitude") is not None and item.get("longitude") is not None)
    )

    queue = build_coordinate_queue(items, args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=== COORDINATE / DETAIL-PAGE QUEUE ===")
    print(f"Eligible enriched survivors: {eligible_count}")
    print(f"Already exact location:      {exact_count}")
    print(f"Queued now:                  {len(queue)}")
    print(f"Deferred for later:          {max(0, eligible_count - len(queue))}")
    print(f"Output:                      {args.output}")

    print()
    for item in queue:
        concerns = ",".join(item["coordinate_queue_concerns"]) or "none"
        print(
            f"#{item['rank']:>2} | {item['listing_id']} | "
            f"q={item['coordinate_queue_score']:>5.1f} | "
            f"base={item.get('aruodas_candidate_score', 0):>5.1f} | "
            f"{item.get('district') or '-'} | {item.get('street') or '-'} | "
            f"{item.get('rent_eur') or '-'} € | concerns={concerns}"
        )
        print(f"     save as: {item['save_as']}")


if __name__ == "__main__":
    main()
