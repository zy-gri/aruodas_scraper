from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATES = Path("data/parsed/aruodas_candidates.json")
DEFAULT_ENRICHMENT = Path("data/enrichment/aruodas_text_enrichment_seed.json")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_candidates_text_enriched.json")

TEXT_ENRICHMENT_VERSION = "aruodas-text-enrichment-v1"

# Only descriptive / restriction fields belong in the search-index sidecar.
# Dynamic facts such as price, rooms, area, floor and reservation status must
# continue to come from the manually saved Aruodas search-page baseline.
ALLOWED_ENRICHMENT_FIELDS = {
    "listing_scope",
    "description_summary",
    "building_type",
    "equipment_state",
    "parking",
    "balcony",
    "terrace",
    "air_conditioning",
    "dishwasher",
    "dryer",
    "recuperation",
    "underfloor_heating",
    "high_ceilings",
    "separate_entrance",
    "multi_level",
    "basement_or_semi_basement",
    "no_window",
    "maximum_occupants",
    "minimum_lease_months",
    "deposit_months",
    "deposit_eur",
    "long_term_only",
    "pets_policy",
    "children_policy",
    "smoking_policy",
    "positive_signals",
    "negative_signals",
    "source_method",
    "source_url",
    "source_checked_at",
}

HARD_REJECT_SCOPES = {
    "room_rental",
    "shared_room",
    "shared_apartment",
    "dormitory",
}


def _normalize_enrichment(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Keep only explicitly allowlisted descriptive enrichment fields."""

    return {
        key: value
        for key, value in enrichment.items()
        if key in ALLOWED_ENRICHMENT_FIELDS
    }


def apply_text_enrichment(
    candidate: dict[str, Any],
    enrichment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach normalized search-index facts without overwriting baseline facts."""

    result = dict(candidate)

    if not enrichment:
        result["text_enrichment_status"] = "missing"
        result["text_enrichment_version"] = TEXT_ENRICHMENT_VERSION
        return result

    normalized = _normalize_enrichment(enrichment)
    result["text_enrichment"] = normalized
    result["text_enrichment_status"] = "enriched"
    result["text_enrichment_version"] = TEXT_ENRICHMENT_VERSION

    reject_reasons = list(result.get("candidate_reject_reasons") or [])

    scope = normalized.get("listing_scope")
    if scope in HARD_REJECT_SCOPES:
        reject_reasons.append(f"Text enrichment identifies listing scope as {scope}.")

    if normalized.get("no_window") is True:
        reject_reasons.append("Text enrichment says the unit has no window.")

    # A semi-basement is suspicious but not an automatic reject by itself.
    # It becomes a hard reject only when a stronger unusable signal exists,
    # such as no_window=True.

    if reject_reasons:
        result["candidate_hard_reject"] = True
        result["candidate_reject_reasons"] = reject_reasons
        result["candidate_tier"] = "REJECT"
        result["candidate_priority"] = 0
        result["post_enrichment_status"] = "REJECT"
    else:
        result["post_enrichment_status"] = "SURVIVOR"

    return result


def merge_text_enrichment(
    candidates: list[dict[str, Any]],
    enrichments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        item["listing_id"]: item
        for item in enrichments
        if item.get("listing_id")
    }

    return [
        apply_text_enrichment(candidate, by_id.get(candidate.get("listing_id")))
        for candidate in candidates
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge normalized Aruodas text/detail enrichment into ranked candidates."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--enrichment", type=Path, default=DEFAULT_ENRICHMENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Candidate dataset not found: {args.input}")
    if not args.enrichment.exists():
        raise FileNotFoundError(f"Enrichment sidecar not found: {args.enrichment}")

    candidates = json.loads(args.input.read_text(encoding="utf-8"))
    enrichments = json.loads(args.enrichment.read_text(encoding="utf-8"))

    merged = merge_text_enrichment(candidates, enrichments)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    enriched_count = sum(
        1 for item in merged if item.get("text_enrichment_status") == "enriched"
    )
    rejected_by_text = sum(
        1
        for item in merged
        if item.get("text_enrichment_status") == "enriched"
        and item.get("post_enrichment_status") == "REJECT"
    )
    enriched_survivors = sum(
        1
        for item in merged
        if item.get("text_enrichment_status") == "enriched"
        and item.get("post_enrichment_status") == "SURVIVOR"
    )

    print()
    print("=== TEXT ENRICHMENT MERGE ===")
    print(f"Candidates:                {len(merged)}")
    print(f"Enrichment records:        {len(enrichments)}")
    print(f"Matched/enriched:          {enriched_count}")
    print(f"Rejected by text:          {rejected_by_text}")
    print(f"Enriched survivors:        {enriched_survivors}")
    print(f"Still missing enrichment:  {len(merged) - enriched_count}")
    print(f"Output:                    {args.output}")

    print()
    print(f"=== TOP {args.top} NON-REJECTED ===")

    shown = 0
    for item in merged:
        if item.get("candidate_tier") == "REJECT":
            continue

        enrichment = item.get("text_enrichment") or {}
        scope = enrichment.get("listing_scope") or "unknown"
        status = item.get("text_enrichment_status")

        print(
            f"{item['listing_id']} | "
            f"{item.get('aruodas_candidate_score', 0):>5.1f} | "
            f"{item.get('candidate_tier', '-'):<9} | "
            f"{item.get('district') or '-'} | "
            f"{item.get('street') or '-'} | "
            f"{item.get('rent_eur') or '-'} € | "
            f"text={status} | scope={scope}"
        )

        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
