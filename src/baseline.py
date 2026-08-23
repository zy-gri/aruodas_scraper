from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.parser import parse_file


BASELINE_DIR = Path("data/raw/baseline_2026-08-23")

OUTPUT_DIR = Path("data/parsed")

BASELINE_OUTPUT = OUTPUT_DIR / "aruodas_baseline_2026-08-23.json"
CURRENT_STATE_OUTPUT = OUTPUT_DIR / "aruodas_current_state.json"


def main():

    print()
    print("=" * 70)
    print("ARUODAS BASELINE IMPORT")
    print("=" * 70)

    if not BASELINE_DIR.exists():
        raise FileNotFoundError(
            f"Baseline directory not found: {BASELINE_DIR}"
        )

    html_files = sorted(
        BASELINE_DIR.glob("*.html")
    )

    if not html_files:
        raise RuntimeError(
            f"No HTML files found in {BASELINE_DIR}"
        )

    print()
    print(f"HTML pages found: {len(html_files)}")

    for path in html_files:
        print(f" - {path.name}")

    all_listings = {}

    total_cards = 0
    duplicate_count = 0

    print()
    print("=" * 70)
    print("PARSING")
    print("=" * 70)

    for path in html_files:

        listings = parse_file(path)

        total_cards += len(listings)

        new_on_page = 0
        duplicates_on_page = 0

        for listing in listings:

            listing_id = listing["listing_id"]

            if listing_id in all_listings:

                duplicate_count += 1
                duplicates_on_page += 1

                continue

            listing["source_file"] = path.name

            all_listings[listing_id] = listing

            new_on_page += 1

        print(
            f"{path.name}: "
            f"{len(listings)} parsed | "
            f"{new_on_page} new | "
            f"{duplicates_on_page} duplicates"
        )

    listings = list(
        all_listings.values()
    )

    # ---------------------------------------------------------
    # Add baseline metadata
    # ---------------------------------------------------------

    baseline_timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    for listing in listings:

        listing["first_seen_at"] = baseline_timestamp
        listing["last_seen_at"] = baseline_timestamp
        listing["baseline"] = True

    # ---------------------------------------------------------
    # Save outputs
    # ---------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    BASELINE_OUTPUT.write_text(
        json.dumps(
            listings,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    CURRENT_STATE_OUTPUT.write_text(
        json.dumps(
            listings,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("BASELINE RESULT")
    print("=" * 70)

    print(f"Pages:             {len(html_files)}")
    print(f"Cards parsed:      {total_cards}")
    print(f"Duplicates:        {duplicate_count}")
    print(f"Unique listings:   {len(listings)}")

    print()
    print("Baseline file:")
    print(BASELINE_OUTPUT)

    print()
    print("Current state:")
    print(CURRENT_STATE_OUTPUT)

    # ---------------------------------------------------------
    # District breakdown
    # ---------------------------------------------------------

    district_counts = Counter(
        listing.get("district")
        for listing in listings
    )

    print()
    print("=" * 70)
    print("DISTRICTS")
    print("=" * 70)

    for district, count in district_counts.most_common():

        print(
            f"{district:<25} {count}"
        )

    # ---------------------------------------------------------
    # Price statistics
    # ---------------------------------------------------------

    rents = [
        listing["rent_eur"]
        for listing in listings
        if listing.get("rent_eur") is not None
    ]

    if rents:

        print()
        print("=" * 70)
        print("RENT RANGE")
        print("=" * 70)

        print(
            f"Minimum: {min(rents):.0f} €"
        )

        print(
            f"Maximum: {max(rents):.0f} €"
        )

        print(
            f"Average: {sum(rents) / len(rents):.0f} €"
        )

    # ---------------------------------------------------------
    # Field completeness
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("FIELD COMPLETENESS")
    print("=" * 70)

    important_fields = [
        "listing_id",
        "url",
        "district",
        "street",
        "rooms",
        "area_m2",
        "floor",
        "floors_total",
        "year_built",
        "heating",
        "rent_eur",
        "price_per_m2",
        "main_image_url",
    ]

    for field in important_fields:

        count = sum(
            1
            for listing in listings
            if listing.get(field) is not None
        )

        print(
            f"{field:<22} "
            f"{count}/{len(listings)}"
        )

    print()
    print("=" * 70)
    print("BASELINE IMPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()