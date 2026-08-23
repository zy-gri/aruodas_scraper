from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


# Aruodas rental listing card
LISTING_SELECTOR = "div.list-row-v2.object-row.srentflat.advert"


def _number(value: str) -> float:
    """
    Convert Lithuanian-style numbers to float.

    Examples:
        "300"   -> 300.0
        "15,08" -> 15.08
        "1 200" -> 1200.0
    """
    value = value.replace(" ", "").replace(",", ".")
    return float(value)


def _clean_url(url: str) -> str:
    """
    Remove search-specific query parameters.

    Example:
        .../?search_pos=1
    becomes:
        .../
    """
    return url.split("?")[0]


def parse_listing(card) -> dict[str, Any] | None:
    """
    Parse one Aruodas rental listing card.
    """

    # ---------------------------------------------------------
    # Remove Aruodas informational tooltip.
    #
    # It contains text such as "1 žvaigždutės kaina – 0,99 €",
    # which would otherwise be mistaken for apartment rent.
    # ---------------------------------------------------------

    for tooltip in card.select(".simple-info-tooltip"):
        tooltip.decompose()

    # ---------------------------------------------------------
    # Find listing image
    #
    # Aruodas conveniently exposes:
    # data-id="1310526"
    # data-objid="4"
    #
    # Together they form:
    # 4-1310526
    # ---------------------------------------------------------

    image = card.select_one("img[data-id][data-objid]")

    if not image:
        return None

    data_id = image.get("data-id")
    object_id = image.get("data-objid")

    if not data_id or not object_id:
        return None

    listing_id = f"{object_id}-{data_id}"

    # ---------------------------------------------------------
    # Listing URL
    # ---------------------------------------------------------

    link = card.find(
        "a",
        href=lambda href: href and "butu-nuoma-kaune" in href,
    )

    url = _clean_url(link["href"]) if link else None

    # ---------------------------------------------------------
    # Location
    #
    # Example ALT:
    # "Šilainiai, Saulėlydžio g., 1 kambario buto nuoma"
    # ---------------------------------------------------------

    alt = image.get("alt", "")

    alt_parts = [
        part.strip()
        for part in alt.split(",")
    ]

    district = alt_parts[0] if len(alt_parts) >= 1 else None
    street = alt_parts[1] if len(alt_parts) >= 2 else None

    # ---------------------------------------------------------
    # Convert card into clean text tokens
    # ---------------------------------------------------------

    tokens = [
        text.strip()
        for text in card.stripped_strings
        if text.strip()
    ]

    raw_text = " | ".join(tokens)

    # ---------------------------------------------------------
    # Listing age
    #
    # Examples:
    # "Prieš 12 val."
    # "Prieš 1 d."
    # ---------------------------------------------------------

    age_text = next(
        (
            token
            for token in tokens
            if token.startswith("Prieš")
        ),
        None,
    )

    # ---------------------------------------------------------
    # Rooms
    #
    # Example:
    # "2 k."
    # ---------------------------------------------------------

    rooms = None

    for token in tokens:
        match = re.fullmatch(
            r"(\d+)\s*k\.",
            token,
        )

        if match:
            rooms = int(match.group(1))
            break

    # ---------------------------------------------------------
    # Area
    #
    # Examples:
    # "45 m²"
    # "49.7 m²"
    # ---------------------------------------------------------

    area_m2 = None

    for token in tokens:
        match = re.fullmatch(
            r"(\d+(?:[.,]\d+)?)\s*m²",
            token,
        )

        if match:
            area_m2 = _number(match.group(1))
            break

    # ---------------------------------------------------------
    # Floor
    #
    # Example:
    # "3/5 aukšt."
    # ---------------------------------------------------------

    floor = None
    floors_total = None
    floor_index = None

    for i, token in enumerate(tokens):
        match = re.fullmatch(
            r"(\d+)/(\d+)\s*aukšt\.",
            token,
        )

        if match:
            floor = int(match.group(1))
            floors_total = int(match.group(2))
            floor_index = i
            break

    # ---------------------------------------------------------
    # Construction / renovation years
    #
    # Examples:
    #
    # 2019 m.
    #
    # or:
    #
    # 2000 m.
    # 2000 m.
    # renovacija
    # ---------------------------------------------------------

    years = []

    for token in tokens:
        match = re.fullmatch(
            r"(\d{4})\s*m\.",
            token,
        )

        if match:
            years.append(int(match.group(1)))

    year_built = years[0] if years else None

    renovation_year = None

    has_renovation = any(
        token.lower() == "renovacija"
        for token in tokens
    )

    if has_renovation and len(years) >= 2:
        renovation_year = years[1]

    # ---------------------------------------------------------
    # Rent
    #
    # Example:
    # "750 €"
    #
    # Important:
    # €/m² is parsed separately.
    # ---------------------------------------------------------

    rent_eur = None
    rent_index = None

    for i, token in enumerate(tokens):
        match = re.fullmatch(
            r"([\d\s]+(?:[.,]\d+)?)\s*€",
            token,
        )

        if match:
            rent_eur = _number(match.group(1))
            rent_index = i

    # ---------------------------------------------------------
    # Price per square metre
    #
    # Example:
    # "15,08 €/m²"
    # ---------------------------------------------------------

    price_per_m2 = None

    for token in tokens:
        match = re.fullmatch(
            r"([\d\s]+(?:[.,]\d+)?)\s*€/m²",
            token,
        )

        if match:
            price_per_m2 = _number(match.group(1))
            break

    # ---------------------------------------------------------
    # Price reduction
    #
    # Example:
    # "Kaina sumažėjusi 12,5%"
    # ---------------------------------------------------------

    price_reduction_pct = None

    for token in tokens:
        match = re.search(
            r"Kaina sumažėjusi\s+([\d,.]+)%",
            token,
            flags=re.IGNORECASE,
        )

        if match:
            price_reduction_pct = _number(
                match.group(1)
            )
            break

    # ---------------------------------------------------------
    # Heating
    #
    # Usually located between floor/year information
    # and rent.
    #
    # Examples:
    # "Dujinis"
    # "Centrinis"
    # "Centrinis kolektorinis"
    # "Aeroterminis"
    # ---------------------------------------------------------

    heating = None

    if (
        floor_index is not None
        and rent_index is not None
        and rent_index > floor_index
    ):
        middle = tokens[
            floor_index + 1 : rent_index
        ]

        ignored_exact = {
            "renovacija",
            "rezervuota",
            "galima su gyvūnais",
        }

        candidates = []

        for token in middle:
            lower = token.lower()

            # Ignore year
            if re.fullmatch(
                r"\d{4}\s*m\.",
                token,
            ):
                continue

            if lower in ignored_exact:
                continue

            if lower.startswith(
                "kaina sumažėjusi"
            ):
                continue

            candidates.append(token)

        if candidates:
            heating = candidates[-1]

    # ---------------------------------------------------------
    # Listing flags
    # ---------------------------------------------------------

    reserved = any(
        token.lower() == "rezervuota"
        for token in tokens
    )

    pets_allowed = any(
        "galima su gyvūnais"
        in token.lower()
        for token in tokens
    )

    # ---------------------------------------------------------
    # Images
    #
    # Search page already exposes:
    #
    # data-default = main photo
    # data-extra   = extra photos
    # ---------------------------------------------------------

    main_image_url = (
        image.get("data-default")
        or image.get("data-src")
    )

    extra_raw = image.get(
        "data-extra",
        "",
    )

    extra_image_urls = [
        image_url.strip()
        for image_url in extra_raw.split(",")
        if image_url.strip()
    ]

    image_urls = []

    if main_image_url:
        image_urls.append(
            main_image_url
        )

    for image_url in extra_image_urls:
        if image_url not in image_urls:
            image_urls.append(
                image_url
            )

    # ---------------------------------------------------------
    # Final normalized listing object
    # ---------------------------------------------------------

    return {
        "source": "aruodas",

        "listing_id": listing_id,
        "url": url,

        "city": "Kaunas",
        "district": district,
        "street": street,

        "listed_age_text": age_text,

        "rooms": rooms,
        "area_m2": area_m2,

        "floor": floor,
        "floors_total": floors_total,

        "year_built": year_built,
        "renovation_year": renovation_year,

        "heating": heating,

        "rent_eur": rent_eur,
        "price_per_m2": price_per_m2,
        "price_reduction_pct": price_reduction_pct,

        "reserved": reserved,
        "pets_allowed": pets_allowed,

        "main_image_url": main_image_url,
        "extra_image_urls": extra_image_urls,
        "image_urls": image_urls,

        "preview_image_count": len(
            image_urls
        ),

        # Keep this during development.
        # Makes parser debugging much easier.
        "raw_text": raw_text,
    }


def parse_html(
    html: str,
) -> list[dict[str, Any]]:
    """
    Parse a complete Aruodas search results page.
    """

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    cards = soup.select(
        LISTING_SELECTOR
    )

    listings = []
    seen_ids = set()

    for card in cards:
        listing = parse_listing(card)

        if not listing:
            continue

        listing_id = listing[
            "listing_id"
        ]

        if listing_id in seen_ids:
            continue

        seen_ids.add(
            listing_id
        )

        listings.append(
            listing
        )

    return listings


def parse_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Parse an HTML file and optionally save
    normalized listings as JSON.
    """

    input_path = Path(
        input_path
    )

    html = input_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    listings = parse_html(
        html
    )

    if output_path:
        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                listings,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return listings

def parse_files(
    input_paths: list[Path],
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Parse multiple Aruodas result pages and merge them
    into one dataset, deduplicated by listing_id.
    """

    all_listings = []
    seen_ids = set()

    print()
    print("=== PARSING SAVED PAGES ===")

    for input_path in input_paths:
        listings = parse_file(input_path)

        new_count = 0
        duplicate_count = 0

        for listing in listings:
            listing_id = listing["listing_id"]

            if listing_id in seen_ids:
                duplicate_count += 1
                continue

            seen_ids.add(listing_id)

            # Useful for debugging which page produced the record
            listing["source_file"] = input_path.name

            all_listings.append(listing)
            new_count += 1

        print(
            f"{input_path.name}: "
            f"{len(listings)} parsed | "
            f"{new_count} new | "
            f"{duplicate_count} duplicates"
        )

    if output_path:
        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                all_listings,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return all_listings

def main():
    raw_dir = Path("data/raw")

    output_path = Path(
        "data/parsed/aruodas_listings_combined.json"
    )

    input_paths = sorted(
        raw_dir.glob("kaunas_rentals*.html")
    )

    if not input_paths:
        raise FileNotFoundError(
            "No saved Aruodas pages found in data/raw/"
        )

    print()
    print("=== ARUODAS MULTI-PAGE PARSER ===")
    print(f"Pages found: {len(input_paths)}")

    for path in input_paths:
        print(f" - {path.name}")

    listings = parse_files(
        input_paths,
        output_path,
    )

    print()
    print("=== COMBINED RESULT ===")
    print(f"Unique listings: {len(listings)}")
    print(f"Output:          {output_path}")

    print()
    print("=== FIRST 10 LISTINGS ===")

    for listing in listings[:10]:
        print(
            f"{listing['listing_id']} | "
            f"{listing['district']} | "
            f"{listing['street']} | "
            f"{listing['rooms']} rooms | "
            f"{listing['area_m2']} m² | "
            f"{listing['rent_eur']} € | "
            f"{listing['heating']} | "
            f"{listing['preview_image_count']} images | "
            f"{listing['source_file']}"
        )

    print()
    print("=== FIELD COMPLETENESS ===")

    fields = [
        "listing_id",
        "url",
        "district",
        "street",
        "rooms",
        "area_m2",
        "floor",
        "floors_total",
        "rent_eur",
        "price_per_m2",
    ]

    for field in fields:
        populated = sum(
            1
            for listing in listings
            if listing.get(field) is not None
        )

        print(
            f"{field:<20} "
            f"{populated}/{len(listings)}"
        )


if __name__ == "__main__":
    main()