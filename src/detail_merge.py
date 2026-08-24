from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.detail_parser import parse_detail_file


DEFAULT_BASELINE = Path("data/parsed/aruodas_baseline_2026-08-23.json")
DEFAULT_DETAIL_DIR = Path("data/raw")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_baseline_location_enriched.json")
DETAIL_FILENAME_RE = re.compile(r"^detail_(?P<listing_id>\d+-\d+)\.html$", re.IGNORECASE)

LOCATION_FIELDS = (
    "latitude",
    "longitude",
    "map_accuracy",
    "location_zone",
    "location_label",
    "location_grade",
    "location_score",
    "location_gate",
    "location_confidence",
    "zone_distance_m",
    "location_rationale",
    "location_classifier_version",
    "coordinates_found",
    "aruodas_map_approximate",
    "detail_source_file",
)


def listing_id_from_detail_filename(path: str | Path) -> str | None:
    path = Path(path)
    match = DETAIL_FILENAME_RE.fullmatch(path.name)
    return match.group("listing_id") if match else None


def _empty_location_fields() -> dict[str, Any]:
    return {
        "latitude": None,
        "longitude": None,
        "map_accuracy": None,
        "location_zone": None,
        "location_label": None,
        "location_grade": None,
        "location_score": None,
        "location_gate": None,
        "location_confidence": None,
        "zone_distance_m": None,
        "location_rationale": None,
        "location_classifier_version": None,
        "coordinates_found": False,
        "aruodas_map_approximate": None,
        "detail_source_file": None,
    }


def merge_detail_locations(
    listings: list[dict[str, Any]],
    detail_paths: list[Path],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge saved detail-page location data into baseline listings.

    Baseline/search-page fields remain the source of truth. This function only
    adds the location/detail fields produced by ``src.detail_parser``.
    """

    enriched = []
    index: dict[str, dict[str, Any]] = {}

    for listing in listings:
        row = dict(listing)
        row.update(_empty_location_fields())
        row["location_enrichment_status"] = "detail_missing"
        enriched.append(row)

        listing_id = row.get("listing_id")
        if listing_id:
            index[str(listing_id)] = row

    matched_files = 0
    coordinates_found = 0
    unmatched_detail_files: list[str] = []
    invalid_detail_filenames: list[str] = []
    duplicate_detail_ids: list[str] = []
    seen_detail_ids: set[str] = set()

    for detail_path in sorted(detail_paths):
        listing_id = listing_id_from_detail_filename(detail_path)
        if not listing_id:
            invalid_detail_filenames.append(detail_path.name)
            continue

        if listing_id in seen_detail_ids:
            duplicate_detail_ids.append(listing_id)
            continue
        seen_detail_ids.add(listing_id)

        row = index.get(listing_id)
        if row is None:
            unmatched_detail_files.append(detail_path.name)
            continue

        detail = parse_detail_file(detail_path)
        matched_files += 1

        # Only copy fields owned by the detail/location layer. Never overwrite
        # rent, rooms, area, search-page reservation state, etc.
        for field in LOCATION_FIELDS:
            if field in detail:
                row[field] = detail[field]

        if detail.get("coordinates_found"):
            coordinates_found += 1
            row["location_enrichment_status"] = "enriched"
        else:
            row["location_enrichment_status"] = "coordinates_missing"

    report = {
        "baseline_listings": len(listings),
        "detail_files": len(detail_paths),
        "matched_detail_files": matched_files,
        "coordinates_found": coordinates_found,
        "baseline_without_detail": sum(
            1 for row in enriched if row["location_enrichment_status"] == "detail_missing"
        ),
        "matched_without_coordinates": sum(
            1
            for row in enriched
            if row["location_enrichment_status"] == "coordinates_missing"
        ),
        "unmatched_detail_files": unmatched_detail_files,
        "invalid_detail_filenames": invalid_detail_filenames,
        "duplicate_detail_ids": duplicate_detail_ids,
    }

    return enriched, report


def run_merge(
    baseline_path: str | Path = DEFAULT_BASELINE,
    detail_dir: str | Path = DEFAULT_DETAIL_DIR,
    output_path: str | Path = DEFAULT_OUTPUT,
    pattern: str = "detail_*.html",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_path = Path(baseline_path)
    detail_dir = Path(detail_dir)
    output_path = Path(output_path)

    listings = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(listings, list):
        raise ValueError("Baseline JSON must contain a list of listing objects.")

    detail_paths = sorted(detail_dir.glob(pattern))
    enriched, report = merge_detail_locations(listings, detail_paths)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report["output_path"] = str(output_path)
    return enriched, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge saved Aruodas detail-page location data into the baseline dataset."
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--detail-dir", default=str(DEFAULT_DETAIL_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--pattern", default="detail_*.html")
    args = parser.parse_args()

    _, report = run_merge(
        baseline_path=args.baseline,
        detail_dir=args.detail_dir,
        output_path=args.output,
        pattern=args.pattern,
    )

    print()
    print("=== DETAIL LOCATION MERGE ===")
    print(f"Baseline listings:            {report['baseline_listings']}")
    print(f"Detail files found:           {report['detail_files']}")
    print(f"Matched detail files:         {report['matched_detail_files']}")
    print(f"Coordinates found:            {report['coordinates_found']}")
    print(f"Baseline without detail:      {report['baseline_without_detail']}")
    print(f"Matched without coordinates:  {report['matched_without_coordinates']}")
    print(f"Unmatched detail files:       {len(report['unmatched_detail_files'])}")
    print(f"Invalid detail filenames:     {len(report['invalid_detail_filenames'])}")
    print(f"Duplicate detail IDs:         {len(report['duplicate_detail_ids'])}")
    print(f"Output:                       {report['output_path']}")

    if report["unmatched_detail_files"]:
        print("Unmatched:", ", ".join(report["unmatched_detail_files"]))


if __name__ == "__main__":
    main()
