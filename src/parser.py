from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


LISTING_SELECTOR = "div.list-row-v2.object-row.srentflat.advert"

# Search cards place heating between the floor/year block and the rent, but
# price-change badges can appear in the same area. Only accept tokens that
# actually look like a heating type; never infer heating from arbitrary text.
HEATING_MARKERS = (
    "centrinis",
    "dujinis",
    "elektra",
    "aeroterminis",
    "geoterminis",
    "kietu kuru",
    "skystu kuru",
    "krosninis",
    "oras-vanduo",
    "oras oras",
    "individualus",
    "kita",
)


def _number(value: str) -> float:
    value = value.replace(" ", "").replace(",", ".")
    return float(value)


def _clean_url(url: str) -> str:
    return url.split("?")[0]


def _looks_like_heating(token: str) -> bool:
    lower = token.strip().lower()

    # Explicit guard for both directions of Aruodas price-change badges.
    if lower.startswith("kaina "):
        return False

    return any(marker in lower for marker in HEATING_MARKERS)


def parse_listing(card) -> dict[str, Any] | None:
    """Parse one Aruodas apartment-rental search-result card."""

    # Tooltips can contain small euro amounts that otherwise look like rent.
    for tooltip in card.select(".simple-info-tooltip"):
        tooltip.decompose()

    image = card.select_one("img[data-id][data-objid]")
    if not image:
        return None

    data_id = image.get("data-id")
    object_id = image.get("data-objid")
    if not data_id or not object_id:
        return None

    listing_id = f"{object_id}-{data_id}"

    link = card.find(
        "a",
        href=lambda href: href and "butu-nuoma-kaune" in href,
    )
    url = _clean_url(link["href"]) if link else None

    alt_parts = [part.strip() for part in image.get("alt", "").split(",")]
    district = alt_parts[0] if len(alt_parts) >= 1 else None
    street = alt_parts[1] if len(alt_parts) >= 2 else None

    tokens = [text.strip() for text in card.stripped_strings if text.strip()]
    raw_text = " | ".join(tokens)

    age_text = next((token for token in tokens if token.startswith("Prieš")), None)

    rooms = None
    for token in tokens:
        match = re.fullmatch(r"(\d+)\s*k\.", token)
        if match:
            rooms = int(match.group(1))
            break

    area_m2 = None
    for token in tokens:
        match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*m²", token)
        if match:
            area_m2 = _number(match.group(1))
            break

    floor = None
    floors_total = None
    floor_index = None
    for index, token in enumerate(tokens):
        match = re.fullmatch(r"(\d+)/(\d+)\s*aukšt\.", token)
        if match:
            floor = int(match.group(1))
            floors_total = int(match.group(2))
            floor_index = index
            break

    years: list[int] = []
    for token in tokens:
        match = re.fullmatch(r"(\d{4})\s*m\.", token)
        if match:
            years.append(int(match.group(1)))

    year_built = years[0] if years else None
    has_renovation = any(token.lower() == "renovacija" for token in tokens)
    renovation_year = years[1] if has_renovation and len(years) >= 2 else None

    rent_eur = None
    rent_index = None
    for index, token in enumerate(tokens):
        match = re.fullmatch(r"([\d\s]+(?:[.,]\d+)?)\s*€", token)
        if match:
            rent_eur = _number(match.group(1))
            rent_index = index

    price_per_m2 = None
    for token in tokens:
        match = re.fullmatch(r"([\d\s]+(?:[.,]\d+)?)\s*€/m²", token)
        if match:
            price_per_m2 = _number(match.group(1))
            break

    price_reduction_pct = None
    for token in tokens:
        match = re.search(
            r"Kaina sumažėjusi\s+([\d,.]+)%",
            token,
            flags=re.IGNORECASE,
        )
        if match:
            price_reduction_pct = _number(match.group(1))
            break

    heating = None
    if floor_index is not None and rent_index is not None and rent_index > floor_index:
        middle = tokens[floor_index + 1 : rent_index]
        heating_candidates = [token for token in middle if _looks_like_heating(token)]
        if heating_candidates:
            heating = heating_candidates[-1]

    reserved = any(token.lower() == "rezervuota" for token in tokens)
    pets_allowed = any("galima su gyvūnais" in token.lower() for token in tokens)

    main_image_url = image.get("data-default") or image.get("data-src")
    extra_raw = image.get("data-extra", "")
    extra_image_urls = [
        image_url.strip()
        for image_url in extra_raw.split(",")
        if image_url.strip()
    ]

    image_urls: list[str] = []
    if main_image_url:
        image_urls.append(main_image_url)
    for image_url in extra_image_urls:
        if image_url not in image_urls:
            image_urls.append(image_url)

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
        "preview_image_count": len(image_urls),
        "raw_text": raw_text,
    }


def parse_html(html: str) -> list[dict[str, Any]]:
    """Parse a complete Aruodas search-results page."""

    soup = BeautifulSoup(html, "lxml")
    listings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for card in soup.select(LISTING_SELECTOR):
        listing = parse_listing(card)
        if not listing:
            continue

        listing_id = listing["listing_id"]
        if listing_id in seen_ids:
            continue

        seen_ids.add(listing_id)
        listings.append(listing)

    return listings


def parse_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Parse one saved search HTML file and optionally write JSON."""

    input_path = Path(input_path)
    html = input_path.read_text(encoding="utf-8", errors="ignore")
    listings = parse_html(html)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(listings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return listings


def parse_files(
    input_paths: list[Path],
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Parse and deduplicate multiple saved Aruodas result pages."""

    all_listings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

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
            listing["source_file"] = input_path.name
            all_listings.append(listing)
            new_count += 1

        print(
            f"{input_path.name}: {len(listings)} parsed | "
            f"{new_count} new | {duplicate_count} duplicates"
        )

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(all_listings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return all_listings


def main() -> None:
    raw_dir = Path("data/raw")
    output_path = Path("data/parsed/aruodas_listings_combined.json")
    input_paths = sorted(raw_dir.glob("kaunas_rentals*.html"))

    if not input_paths:
        raise FileNotFoundError("No saved Aruodas pages found in data/raw/")

    print()
    print("=== ARUODAS MULTI-PAGE PARSER ===")
    print(f"Pages found: {len(input_paths)}")
    for path in input_paths:
        print(f" - {path.name}")

    listings = parse_files(input_paths, output_path)

    print()
    print("=== COMBINED RESULT ===")
    print(f"Unique listings: {len(listings)}")
    print(f"Output:          {output_path}")

    print()
    print("=== FIRST 10 LISTINGS ===")
    for listing in listings[:10]:
        print(
            f"{listing['listing_id']} | {listing['district']} | {listing['street']} | "
            f"{listing['rooms']} rooms | {listing['area_m2']} m² | "
            f"{listing['rent_eur']} € | {listing['heating']} | "
            f"{listing['preview_image_count']} images | {listing['source_file']}"
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
        populated = sum(1 for listing in listings if listing.get(field) is not None)
        print(f"{field:<20} {populated}/{len(listings)}")


if __name__ == "__main__":
    main()
