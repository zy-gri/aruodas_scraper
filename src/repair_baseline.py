from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from src.parser import parse_file


RAW_BASELINE_DIR = Path("data/raw/baseline_2026-08-23")
BASELINE_PATH = Path("data/parsed/aruodas_baseline_2026-08-23.json")
CURRENT_STATE_PATH = Path("data/parsed/aruodas_current_state.json")

# Fields whose source of truth is the saved Aruodas search-result HTML.
# Metadata/enrichment fields such as first_seen_at, last_seen_at, baseline,
# coordinates, location scores, etc. are deliberately NOT replaced.
SEARCH_PAGE_FIELDS = [
    "source",
    "url",
    "city",
    "district",
    "street",
    "listed_age_text",
    "rooms",
    "area_m2",
    "floor",
    "floors_total",
    "year_built",
    "renovation_year",
    "heating",
    "rent_eur",
    "price_per_m2",
    "price_reduction_pct",
    "reserved",
    "pets_allowed",
    "main_image_url",
    "extra_image_urls",
    "image_urls",
    "preview_image_count",
    "raw_text",
    "source_file",
]


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_raw_baseline() -> dict[str, dict[str, Any]]:
    if not RAW_BASELINE_DIR.exists():
        raise FileNotFoundError(f"Baseline raw directory not found: {RAW_BASELINE_DIR}")

    html_files = sorted(RAW_BASELINE_DIR.glob("*.html"))
    if not html_files:
        raise RuntimeError(f"No HTML files found in {RAW_BASELINE_DIR}")

    reparsed: dict[str, dict[str, Any]] = {}

    for path in html_files:
        for listing in parse_file(path):
            listing_id = listing["listing_id"]
            if listing_id in reparsed:
                continue

            listing["source_file"] = path.name
            reparsed[listing_id] = listing

    return reparsed


def repair_dataset(
    existing: list[dict[str, Any]],
    reparsed: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    existing_ids = {row["listing_id"] for row in existing}
    reparsed_ids = set(reparsed)

    if existing_ids != reparsed_ids:
        missing_from_raw = sorted(existing_ids - reparsed_ids)
        unexpected_in_raw = sorted(reparsed_ids - existing_ids)
        raise RuntimeError(
            "Listing-ID mismatch; refusing to rewrite dataset. "
            f"Missing from raw: {missing_from_raw[:10]} | "
            f"Unexpected in raw: {unexpected_in_raw[:10]}"
        )

    changed_fields: Counter[str] = Counter()
    changed_listings = 0
    repaired_rows: list[dict[str, Any]] = []

    for original in existing:
        listing_id = original["listing_id"]
        fresh = reparsed[listing_id]
        repaired = dict(original)
        listing_changed = False

        for field in SEARCH_PAGE_FIELDS:
            fresh_value = fresh.get(field)
            old_value = repaired.get(field)

            if old_value != fresh_value:
                changed_fields[field] += 1
                listing_changed = True

            repaired[field] = fresh_value

        if listing_changed:
            changed_listings += 1

        repaired_rows.append(repaired)

    return repaired_rows, changed_fields, changed_listings


def backup_once(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".pre_parser_repair.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def repair_file(
    path: Path,
    reparsed: dict[str, dict[str, Any]],
) -> tuple[Counter[str], int, Path]:
    if not path.exists():
        raise FileNotFoundError(path)

    existing = load_json(path)
    repaired, changed_fields, changed_listings = repair_dataset(existing, reparsed)
    backup = backup_once(path)
    save_json(path, repaired)

    return changed_fields, changed_listings, backup


def main() -> None:
    print()
    print("=== BASELINE PARSER REPAIR ===")
    print("Reparsing original saved search pages with the current parser...")

    reparsed = parse_raw_baseline()
    print(f"Reparsed unique listings: {len(reparsed)}")

    for path in (BASELINE_PATH, CURRENT_STATE_PATH):
        changed_fields, changed_listings, backup = repair_file(path, reparsed)

        print()
        print(f"File:             {path}")
        print(f"Listings changed: {changed_listings}")
        print(f"Backup:           {backup}")

        if changed_fields:
            print("Changed fields:")
            for field, count in changed_fields.most_common():
                print(f"  {field:<24} {count}")
        else:
            print("Changed fields:   none")

    print()
    print("Repair complete. Existing timestamps and enrichment fields were preserved.")


if __name__ == "__main__":
    main()
