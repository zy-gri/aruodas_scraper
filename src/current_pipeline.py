from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.candidates import rank_listings
from src.detail_merge import run_merge
from src.enrichment_io import DEFAULT_ENRICHMENT_DIR, load_enrichments
from src.text_enrichment import merge_text_enrichment


DEFAULT_STATE = Path("data/parsed/aruodas_current_state.json")
DEFAULT_DETAIL_DIR = Path("data/raw")
DEFAULT_LOCATION_OUTPUT = Path("data/parsed/aruodas_current_state_location_enriched.json")
DEFAULT_CANDIDATES_OUTPUT = Path("data/parsed/aruodas_candidates.json")
DEFAULT_TEXT_OUTPUT = Path("data/parsed/aruodas_candidates_text_enriched.json")

PIPELINE_VERSION = "aruodas-current-pipeline-v1"


def active_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return listings that are not explicitly marked inactive."""

    return [item for item in items if item.get("is_active", True) is not False]


def build_current_views(
    location_enriched: list[dict[str, Any]],
    enrichments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build ranked and text-enriched views from canonical current state."""

    ranked = rank_listings(active_records(location_enriched))
    text_enriched = merge_text_enrichment(ranked, enrichments)
    return ranked, text_enriched


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the operational Aruodas candidate views from canonical current state, "
            "saved detail-page locations and text enrichment sidecars."
        )
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--detail-dir", type=Path, default=DEFAULT_DETAIL_DIR)
    parser.add_argument("--enrichment", type=Path, default=DEFAULT_ENRICHMENT_DIR)
    parser.add_argument("--location-output", type=Path, default=DEFAULT_LOCATION_OUTPUT)
    parser.add_argument("--candidates-output", type=Path, default=DEFAULT_CANDIDATES_OUTPUT)
    parser.add_argument("--text-output", type=Path, default=DEFAULT_TEXT_OUTPUT)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    if not args.state.exists():
        raise FileNotFoundError(f"Current state not found: {args.state}")

    location_enriched, location_report = run_merge(
        baseline_path=args.state,
        detail_dir=args.detail_dir,
        output_path=args.location_output,
    )

    enrichments = load_enrichments(args.enrichment)
    ranked, text_enriched = build_current_views(location_enriched, enrichments)

    _write_json(args.candidates_output, ranked)
    _write_json(args.text_output, text_enriched)

    exact = sum(1 for item in ranked if item.get("candidate_location_source") == "coordinates")
    text_count = sum(1 for item in text_enriched if item.get("text_enrichment_status") == "enriched")
    rejected = sum(1 for item in text_enriched if item.get("candidate_tier") == "REJECT")

    tiers: dict[str, int] = {}
    for item in text_enriched:
        tier = item.get("candidate_tier") or "UNKNOWN"
        tiers[tier] = tiers.get(tier, 0) + 1

    print()
    print("=== CURRENT ARUODAS PIPELINE ===")
    print(f"Version:                  {PIPELINE_VERSION}")
    print(f"Current state rows:       {len(location_enriched)}")
    print(f"Active rows ranked:       {len(ranked)}")
    print(f"Inactive excluded:        {len(location_enriched) - len(ranked)}")
    print(f"Exact locations:          {exact}")
    print(f"Text enriched:            {text_count}")
    print(f"Rejected after text:      {rejected}")
    print(f"HIGH:                     {tiers.get('HIGH', 0)}")
    print(f"PROMISING:                {tiers.get('PROMISING', 0)}")
    print(f"MAYBE:                    {tiers.get('MAYBE', 0)}")
    print(f"LOW:                      {tiers.get('LOW', 0)}")
    print(f"REJECT:                   {tiers.get('REJECT', 0)}")
    print(f"Location view:            {args.location_output}")
    print(f"Candidates:               {args.candidates_output}")
    print(f"Text-enriched candidates: {args.text_output}")
    print(
        f"Detail merge:             {location_report['matched_detail_files']} matched / "
        f"{location_report['coordinates_found']} with coordinates"
    )

    print()
    print(f"=== TOP {args.top} NON-REJECTED ===")
    shown = 0
    for item in text_enriched:
        if item.get("candidate_tier") == "REJECT":
            continue
        enrichment = item.get("text_enrichment") or {}
        print(
            f"{item['listing_id']} | "
            f"{item.get('aruodas_candidate_score', 0):>5.1f} | "
            f"{item.get('candidate_tier', '-'):<9} | "
            f"{item.get('district') or '-'} | {item.get('street') or '-'} | "
            f"{item.get('rooms') or '-'}r | {item.get('area_m2') or '-'} m² | "
            f"{item.get('rent_eur') or '-'} € | "
            f"loc={item.get('candidate_location_source')} | "
            f"text={item.get('text_enrichment_status')} | "
            f"scope={enrichment.get('listing_scope') or 'unknown'}"
        )
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
