from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.enrichment_io import DEFAULT_ENRICHMENT_DIR, load_enrichments


DEFAULT_CANDIDATES = Path("data/parsed/aruodas_candidates.json")
DEFAULT_ENRICHMENT = DEFAULT_ENRICHMENT_DIR
DEFAULT_OUTPUT = Path("data/parsed/aruodas_text_enrichment_queue.json")


def build_enrichment_queue(
    candidates: list[dict[str, Any]],
    enrichments: list[dict[str, Any]],
    limit: int = 30,
) -> list[dict[str, Any]]:
    enriched_ids = {
        item["listing_id"]
        for item in enrichments
        if item.get("listing_id")
    }

    queue: list[dict[str, Any]] = []

    for candidate in candidates:
        if candidate.get("candidate_tier") == "REJECT":
            continue

        listing_id = candidate.get("listing_id")

        queue.append(
            {
                "rank": len(queue) + 1,
                "listing_id": listing_id,
                "url": candidate.get("url"),
                "district": candidate.get("district"),
                "street": candidate.get("street"),
                "rooms": candidate.get("rooms"),
                "area_m2": candidate.get("area_m2"),
                "rent_eur": candidate.get("rent_eur"),
                "aruodas_candidate_score": candidate.get("aruodas_candidate_score"),
                "candidate_tier": candidate.get("candidate_tier"),
                "coordinate_enrichment_priority": candidate.get(
                    "coordinate_enrichment_priority"
                ),
                "text_enrichment_status": (
                    "already_enriched" if listing_id in enriched_ids else "needed"
                ),
            }
        )

        if len(queue) >= limit:
            break

    return queue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small high-priority queue for Aruodas text enrichment."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument(
        "--enrichment",
        type=Path,
        default=DEFAULT_ENRICHMENT,
        help="One enrichment JSON file or a directory of enrichment sidecars.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Candidate dataset not found: {args.input}")

    candidates = json.loads(args.input.read_text(encoding="utf-8"))
    enrichments = load_enrichments(args.enrichment)

    queue = build_enrichment_queue(candidates, enrichments, args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    already = sum(
        1 for item in queue if item["text_enrichment_status"] == "already_enriched"
    )

    print()
    print("=== TEXT ENRICHMENT QUEUE ===")
    print(f"Queue size:               {len(queue)}")
    print(f"Already enriched:         {already}")
    print(f"Still need enrichment:    {len(queue) - already}")
    print(f"Output:                   {args.output}")

    print()
    for item in queue:
        print(
            f"#{item['rank']:>2} | {item['listing_id']} | "
            f"{item.get('aruodas_candidate_score', 0):>5.1f} | "
            f"{item.get('candidate_tier', '-'):<9} | "
            f"{item.get('district') or '-'} | "
            f"{item.get('street') or '-'} | "
            f"{item.get('rent_eur') or '-'} € | "
            f"text={item['text_enrichment_status']}"
        )


if __name__ == "__main__":
    main()
