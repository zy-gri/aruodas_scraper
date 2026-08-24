from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/parsed/aruodas_baseline_location_enriched.json")
FALLBACK_INPUT = Path("data/parsed/aruodas_baseline_2026-08-23.json")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_candidates.json")

SCORER_VERSION = "aruodas-candidate-v2"


# ---------------------------------------------------------------------------
# First-pass street proxies used only when exact Aruodas coordinates are not
# available yet. These are STR-investigation heuristics, not official zones.
# Exact coordinate classification always overrides these proxies.
# ---------------------------------------------------------------------------

PRIME_STREET_POINTS = {
    "laisvės al.": 35.0,
    "vilniaus g.": 35.0,
    "rotušės a.": 35.0,
    "maironio g.": 34.0,
    "kęstučio g.": 34.0,
    "k. donelaičio g.": 34.0,
    "m. daukšos g.": 34.0,
    "m. valančiaus g.": 34.0,
    "s. dauganto g.": 33.0,
    "gedimino g.": 33.0,
}

STRONG_STREET_POINTS = {
    "karaliaus mindaugo pr.": 31.0,
    "šv. gertrūdos g.": 31.0,
    "kurpių g.": 32.0,
    "v. putvinskio g.": 30.0,
    "j. naugardo g.": 30.0,
    "druskininkų g.": 30.0,
    "trimito g.": 30.0,
    "karo ligoninės g.": 29.0,
}

# These can be good, but the exact point matters enough that we do not award
# prime location points until a detail page gives us coordinates.
UNCERTAIN_STREET_POINTS = {
    "brastos g.": 24.0,
    "vytauto pr.": 24.0,
    "parodos g.": 22.0,
    "savanorių pr.": 18.0,
    "zanavykų g.": 18.0,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalise(value: Any) -> str:
    return str(value or "").strip().casefold()


def _location_component(
    listing: dict[str, Any],
) -> tuple[float, str, str, str]:
    """Return location points (0-35), source, confidence and explanation."""

    exact_score = listing.get("location_score")
    zone = listing.get("location_zone")

    if exact_score is not None and zone:
        points = _clamp(float(exact_score) / 100.0 * 35.0, 0.0, 35.0)
        return (
            points,
            "coordinates",
            "high",
            f"Exact micro-zone: {zone} ({exact_score}/100).",
        )

    district = _normalise(listing.get("district"))
    street = _normalise(listing.get("street"))

    for street_name, points in PRIME_STREET_POINTS.items():
        if street == street_name.casefold():
            return (
                points,
                "street_proxy",
                "medium",
                "Prime central street proxy; coordinates should still confirm the exact micro-location.",
            )

    for street_name, points in STRONG_STREET_POINTS.items():
        if street == street_name.casefold():
            return (
                points,
                "street_proxy",
                "medium",
                "Strong central street proxy; coordinates are still preferred.",
            )

    for street_name, points in UNCERTAIN_STREET_POINTS.items():
        if street == street_name.casefold():
            if street_name == "brastos g.":
                note = (
                    "Brastos g. can be excellent if the exact point is Piliamiestis; "
                    "coordinates are required before treating it as a premium zone."
                )
            elif street_name == "savanorių pr.":
                note = (
                    "Savanorių pr. varies strongly by exact position and is not treated "
                    "as prime Centras without coordinates."
                )
            else:
                note = "Potentially useful street, but exact position materially changes STR quality."

            return points, "street_proxy", "low", note

    # District-only fallbacks are deliberately conservative. V1 awarded 30/35
    # to every Centras listing, which made the candidate pool far too broad.
    if district == "senamiestis":
        return (
            27.0,
            "district_proxy",
            "low",
            "Senamiestis district proxy only; exact street/coordinates are not yet known.",
        )
    if district == "centras":
        return (
            23.0,
            "district_proxy",
            "low",
            "Centras district proxy only; this is not enough to assume prime STR location.",
        )
    if district in {"žaliakalnis", "zaliakalnis"}:
        return (
            15.0,
            "district_proxy",
            "low",
            "Žaliakalnis is attractive mainly in its lower/central part; exact location matters.",
        )
    if district in {"vilijampolė", "vilijampole"}:
        return (
            7.0,
            "district_proxy",
            "low",
            "Generic Vilijampolė is weak for our STR thesis unless coordinates prove Piliamiestis or another exceptional pocket.",
        )

    return (
        5.0,
        "district_proxy",
        "low",
        "Location is outside the current preferred core or not mapped yet.",
    )


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


def _enrichment_priority(
    *,
    hard_reject: bool,
    location_source: str,
    location_confidence: str,
    location_points: float,
    score: float,
) -> tuple[str, int]:
    """Prioritise which unresolved listings deserve detail-page coordinates."""

    if hard_reject:
        return "SKIP", 0

    if location_source == "coordinates":
        return "DONE", 0

    # Prime/strong streets with good overall economics should be enriched first.
    if location_points >= 29.0 and score >= 74.0:
        return "HIGH", 3

    # Uncertain streets are specifically valuable to resolve when the rest of
    # the listing is attractive (e.g. Brastos -> Piliamiestis or not).
    if location_confidence == "low" and location_source == "street_proxy" and score >= 70.0:
        return "HIGH", 3

    if score >= 68.0:
        return "MEDIUM", 2

    return "LOW", 1


def score_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Score one listing for *investigation priority*, not profitability."""

    scored = dict(listing)

    hard_reject_reasons: list[str] = []
    if listing.get("reserved"):
        hard_reject_reasons.append("Listing is reserved.")

    (
        location_points,
        location_source,
        location_confidence,
        location_note,
    ) = _location_component(listing)
    rent_points, rent_note = _rent_component(listing.get("rent_eur"))
    layout_points, layout_note = _layout_component(listing)
    building_points, building_note = _building_component(listing)

    raw_score = location_points + rent_points + layout_points + building_points
    score = round(_clamp(raw_score, 0.0, 100.0), 1)

    if hard_reject_reasons:
        tier = "REJECT"
        priority = 0
    elif score >= 86:
        tier = "HIGH"
        priority = 4
    elif score >= 78:
        tier = "PROMISING"
        priority = 3
    elif score >= 68:
        tier = "MAYBE"
        priority = 2
    else:
        tier = "LOW"
        priority = 1

    enrichment_label, enrichment_priority = _enrichment_priority(
        hard_reject=bool(hard_reject_reasons),
        location_source=location_source,
        location_confidence=location_confidence,
        location_points=location_points,
        score=score,
    )

    scored.update(
        {
            "aruodas_candidate_score": score,
            "candidate_tier": tier,
            "candidate_priority": priority,
            "candidate_hard_reject": bool(hard_reject_reasons),
            "candidate_reject_reasons": hard_reject_reasons,
            "candidate_location_source": location_source,
            "candidate_location_confidence": location_confidence,
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
            "coordinate_enrichment_priority": enrichment_label,
            "coordinate_enrichment_priority_value": enrichment_priority,
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
    enrichment_counts: dict[str, int] = {}

    for listing in ranked:
        tier = listing["candidate_tier"]
        tiers[tier] = tiers.get(tier, 0) + 1

        enrichment = listing["coordinate_enrichment_priority"]
        enrichment_counts[enrichment] = enrichment_counts.get(enrichment, 0) + 1

    exact_location_count = sum(
        1 for listing in ranked if listing["candidate_location_source"] == "coordinates"
    )

    print()
    print("=== ARUODAS CANDIDATE RANKING ===")
    print(f"Scorer:                   {SCORER_VERSION}")
    print(f"Input:                    {input_path}")
    print(f"Listings:                 {len(ranked)}")
    print(f"Exact locations:          {exact_location_count}")
    print(f"Need coordinate enrich:   {len(ranked) - exact_location_count}")
    print(f"HIGH:                     {tiers.get('HIGH', 0)}")
    print(f"PROMISING:                {tiers.get('PROMISING', 0)}")
    print(f"MAYBE:                    {tiers.get('MAYBE', 0)}")
    print(f"LOW:                      {tiers.get('LOW', 0)}")
    print(f"REJECT:                   {tiers.get('REJECT', 0)}")
    print(f"Enrich HIGH:              {enrichment_counts.get('HIGH', 0)}")
    print(f"Enrich MEDIUM:            {enrichment_counts.get('MEDIUM', 0)}")
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
            f"loc={listing['candidate_location_source']} | "
            f"enrich={listing['coordinate_enrichment_priority']}"
        )
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
