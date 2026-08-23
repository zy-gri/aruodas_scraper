from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from src.location import classify_location, extract_aruodas_coordinates


APPROXIMATE_MAP_RE = re.compile(
    r"taškas\s*(?:<[^>]+>\s*)*netikslus",
    flags=re.IGNORECASE,
)


def aruodas_marks_map_approximate(html: str) -> bool:
    """Return True when the detail page labels its map point as inaccurate."""

    soup = BeautifulSoup(html, "lxml")

    sublabel = soup.select_one(
        ".show-map-line-inner .sublabel, .map__label .sublabel"
    )

    if sublabel:
        text = " ".join(sublabel.stripped_strings).lower()
        if "netikslus" in text:
            return True

    return bool(APPROXIMATE_MAP_RE.search(html))


def parse_detail_html(html: str) -> dict[str, Any]:
    """Parse location data from a saved Aruodas apartment detail page.

    This module does not fetch Aruodas. It only works with HTML that has
    already been saved from a normal browser session.
    """

    approximate = aruodas_marks_map_approximate(html)
    coordinates = extract_aruodas_coordinates(html)

    if not coordinates:
        return {
            "coordinates_found": False,
            "aruodas_map_approximate": approximate,
            "latitude": None,
            "longitude": None,
            "map_accuracy": "approximate" if approximate else "unknown",
            "location_zone": None,
            "location_label": None,
            "location_grade": None,
            "location_score": None,
            "location_gate": None,
            "location_confidence": None,
            "zone_distance_m": None,
            "location_rationale": None,
            "location_classifier_version": None,
        }

    lat, lon = coordinates
    result = classify_location(lat, lon)

    # Preserve the classifier output while recording what the Aruodas page
    # itself says about the accuracy of this particular map point.
    result["coordinates_found"] = True
    result["aruodas_map_approximate"] = approximate
    result["map_accuracy"] = "approximate" if approximate else "unknown"

    return result


def parse_detail_file(path: str | Path) -> dict[str, Any]:
    """Read a saved detail HTML file and return normalized location fields."""

    path = Path(path)
    html = path.read_text(encoding="utf-8", errors="ignore")
    result = parse_detail_html(html)
    result["detail_source_file"] = path.name
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse location data from a saved Aruodas detail page."
    )
    parser.add_argument("html_file", help="Path to saved Aruodas detail HTML")
    args = parser.parse_args()

    result = parse_detail_file(args.html_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
