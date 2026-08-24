from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/parsed/aruodas_baseline_location_enriched.json")
FALLBACK_INPUT = Path("data/parsed/aruodas_baseline_2026-08-23.json")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_candidates.json")

SCORER_VERSION = "aruodas-candidate-v1"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _location_component(listing: dict[str, Any]) -> tuple[float, str, str]:
    """Return location points (0-35), source and explanation.

    Exact micro-location enrichment wins whenever available. Otherwise use a
    deliberately conservative district/street proxy until a saved detail page
    gives us coordinates.
    """

    exact_score = listing.get("location_score")
    zone = listing.get("location_zone")

    if exact_score is not None and zone:
        points = _clamp(float(exact_score) / 100.0 * 35.0, 0.0, 35.0)
        return (
            points,
            "coordinates",
            f"Exact micro-zone: {zone} ({exact_score}/100).",
        )

    district = (listing.get("district") or "").strip().lower()
    street = (listing.get("street") or "").strip().lower()

    # Brastos is only a hint. It does NOT automatically mean Piliamiestis.
    if "brastos" in street:
        return (
            24.0,
            "street_proxy",
            "Brastos g. is potentially interesting, but coordinates are required to confirm Piliamiestis.",
        )

    if district == "senamiestis":
        return 32.0, "district_proxy", "Senamiestis proxy; exact micro-location not yet known."
    if district == "centras":
        return 30.0, "district_proxy", "Centras proxy; exact micro-location not yet known."
    if district in {"žaliakalnis", "zaliakalnis"}:
        return 21.0, "district_proxy", "Žaliakalnis proxy; strong only in the central/lower part."
    if district == "vilijampolė" or district == "vilijampole":
        return 10.0, "district_proxy", "Generic Vilijampolė is weak for our STR thesis unless exact location proves otherwise."

    return 8.0, "district_proxy", "Location is outside the current preferred core or not mapped yet."


def _rent_component(rent_eur: Any) -> tuple[float, str]:
    """Return rent opportunity points (0-30).

    This is intentionally only an acquisition-cost heuristic. It is NOT a
    profitability estimate and will later be replaced/augmented by Airbnb
    comparable revenue.
    """

    if rent_eur is None:
        return 0.0, "Rent missing."

    rent = float(rent_eur)

    if rent <= 400:
        return 30.0, "Very low asking rent."
    if rent <= 500:
        return 28.0, "Low asking rent."
    if rent <= 600:
        return 25.0, "Attractive asking rent."
    if rent <= 700:
        return 21.0, "Moderate asking rent."
    if rent <= 800:
        return 17.0, "Rent is workable only with strong location/property quality."
    if rent <= 900:
        return 12.0, "High rent; needs strong Airbnb economics."
    if rent <= 1100:
        return 6.0, "Very high rent for a first-pass candidate."

    return 0.0, "Rent is too high to earn first-pass opportunity points."


def _layout_component(listing: dict[str, Any]) -> tuple[float, str]:
    """Return basic layout points (0-20) from rooms and area only."""

    rooms = listing.get("rooms")
    area = listing.get("area_m2")

    if rooms is None or area is None:
        return 5.0, "Layout data incomplete."

    rooms = int(rooms)
    area = float(area)
    points = 0.0
    notes: list[str] = []

    if area < 18:
        points += 1.0
        notes.append("very small")
    elif area < 25:
        points += 5.0
        notes.append("small studio footprint")
    elif area <= 45:
        points += 10.0
        notes.append("efficient STR-sized footprint")
    elif area <= 65:
        points += 9.0
        notes.append("good medium-size footprint")
    elif area <= 85:
        points += 7.0
        notes.append("larger unit")
    else:
        points += 4.0
        notes.append("large footprint increases rent/furnishing burden")

    if rooms == 1:
        points += 6.0
        notes.append("1-room")
    elif rooms == 2:
        points += 10.0
        notes.append("2-room")
    elif rooms == 3:
        points += 8.0
        notes.append("3-room")
    elif rooms >= 4:
        points += 5.0
        notes.append("4+ rooms")

    return _clamp(points, 0.0, 20.0), ", ".join(notes) + "."


def _building_component(listing: dict[str, Any]) -> tuple[float, str]:
    """Return building/renovation points (0-15) from search-card facts."""

    year = listing.get("year_built")
    renovation = listing.get("renovation_year")

    if renovation:
        renovation = int(renovation)
        if renovation >= 2015:
            return 15.0, f"Recently renovated ({renovation})."
        if renovation >= 2005:
            return 12.0, f"Renovated ({renovation})."
        return 9.0, f"Older renovation ({renovation})."

    if year is None:
        return 6.0, "Building age unknown."

    year = int(year)
    if year >= 2020:
        return 15.0, f"Very new building ({year})."
    if year >= 2010:
        return 13.0, f"Modern building ({year})."
    if year >= 2000:
        return 10.0, f"Relatively modern building ({year})."
    if year >= 1940:
        return 6.0, f"Older building ({year}); interior quality matters more than age alone."

    return 8.0, f"Historic building ({year}); can be attractive but needs manual quality review."


def score_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Score one listing for *investigation priority*, not profitability."""

    scored = dict(listing)

    hard_reject_reasons: list[str] = []
    if listing.get("reserved"):
        hard_reject_reasons.append("Listing is reserved.")

    location_points, location_source, location_note = _location_component(listing)
    rent_points, rent_note = _rent_component(listing.get("rent_eur"))
    layout_points, layout_note = _layout_component(listing)
    building_points, building_note = _building_component(listing)

    raw_score = location_points + rent_points + layout_points + building_points
    score = round(_clamp(raw_score, 0.0, 100.0), 1)

    if hard_reject_reasons:
        tier = "REJECT"
        priority = 0
    elif score >= 75:
        tier = "HIGH"
        priority = 4
    elif score >= 60:
        tier = "PROMISING"
        priority = 3
    elif score >= 45:
        tier = "MAYBE"
        priority = 2
    else:
        tier = "LOW"
        priority = 1

    scored.update(
        {
            "aruodas_candidate_score": score,
            "candidate_tier": tier,
            "candidate_priority": priority,
            "candidate_hard_reject": bool(hard_reject_reasons),
            "candidate_reject_reasons": hard_reject_reasons,
            "candidate_location_source": location_source,
            "candidate_score_components": {
                "location": round(location_points, 1),
                "rent": round(rent_points, 1),
                "layout": round(layout_points, 1),
                "building": round(building_points, 1),
            },
            "candidate_reasons": [
                location_note,
                rent_note,
                layout_note,
                building_note,
            ],
            "needs_coordinate_enrichment": location_source != "coordinates",
            "candidate_scorer_version": SCORER_VERSION,
        }
    )

    return scored


def rank_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = [score_listing(listing) for listing in listings]
    return sorted(
        scored,
        key=lambda item: (
            item["candidate_priority"],
            item["aruodas_candidate_score"],
            -(float(item.get("rent_eur") or 10_000)),
        ),
        reverse=True,
    )


def _choose_input(path: Path | None) -> Path:
    if path is not None:
        return path
    if DEFAULT_INPUT.exists():
        return DEFAULT_INPUT
    return FALLBACK_INPUT


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank Aruodas listings for manual rental-arbitrage investigation."
    )
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    input_path = _choose_input(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")

    listings = json.loads(input_path.read_text(encoding="utf-8"))
    ranked = rank_listings(listings)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tiers: dict[str, int] = {}
    for listing in ranked:
        tier = listing["candidate_tier"]
        tiers[tier] = tiers.get(tier, 0) + 1

    exact_location_count = sum(
        1 for listing in ranked if listing["candidate_location_source"] == "coordinates"
    )

    print()
    print("=== ARUODAS CANDIDATE RANKING ===")
    print(f"Input:                    {input_path}")
    print(f"Listings:                 {len(ranked)}")
    print(f"Exact locations:          {exact_location_count}")
    print(f"Need coordinate enrich:   {len(ranked) - exact_location_count}")
    print(f"HIGH:                     {tiers.get('HIGH', 0)}")
    print(f"PROMISING:                {tiers.get('PROMISING', 0)}")
    print(f"MAYBE:                    {tiers.get('MAYBE', 0)}")
    print(f"LOW:                      {tiers.get('LOW', 0)}")
    print(f"REJECT:                   {tiers.get('REJECT', 0)}")
    print(f"Output:                   {args.output}")

    print()
    print(f"=== TOP {min(args.top, len(ranked))} ===")

    shown = 0
    for listing in ranked:
        if listing["candidate_tier"] == "REJECT":
            continue
        print(
            f"{listing['listing_id']} | "
            f"{listing['aruodas_candidate_score']:>5.1f} | "
            f"{listing['candidate_tier']:<9} | "
            f"{listing.get('district') or '-'} | "
            f"{listing.get('street') or '-'} | "
            f"{listing.get('rooms') or '-'}r | "
            f"{listing.get('area_m2') or '-'} m² | "
            f"{listing.get('rent_eur') or '-'} € | "
            f"loc={listing['candidate_location_source']}"
        )
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
