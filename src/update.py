from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.parser import parse_file


DEFAULT_INBOX = Path("data/raw/inbox")
DEFAULT_PROCESSED = Path("data/raw/processed")
DEFAULT_STATE = Path("data/parsed/aruodas_current_state.json")
DEFAULT_REPORT_DIR = Path("data/parsed/update_reports")
DEFAULT_HISTORY_DIR = Path("data/parsed/state_history")

UPDATE_VERSION = "aruodas-update-v1"

# Fields that define a meaningful listing change. Deliberately exclude
# listed_age_text/raw_text and image CDN URLs so ordinary page churn does not
# make every observed listing look updated.
TRACKED_FIELDS = (
    "district",
    "street",
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
    "preview_image_count",
)

# Parser-owned fields that may safely refresh whenever a listing is observed.
# Unknown state/enrichment metadata is preserved because updates start from a
# copy of the existing record and only replace these fields.
REFRESH_FIELDS = (
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
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp(iso_timestamp: str) -> str:
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _meaningful_changes(
    old: dict[str, Any],
    new: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for field in TRACKED_FIELDS:
        old_value = old.get(field)
        new_value = new.get(field)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}
    return changes


def parse_inbox(
    input_paths: list[Path],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse saved result pages and dedupe by listing_id.

    If duplicate cards disagree on tracked fields, the first occurrence is
    retained and the conflict is reported instead of silently choosing one.
    """

    by_id: dict[str, dict[str, Any]] = {}
    parsed_cards = 0
    duplicates = 0
    duplicate_conflicts: list[dict[str, Any]] = []
    per_file: list[dict[str, Any]] = []

    for path in input_paths:
        listings = parse_file(path)
        parsed_cards += len(listings)
        file_new = 0
        file_duplicates = 0

        for listing in listings:
            listing_id = listing["listing_id"]
            listing["source_file"] = path.name

            if listing_id not in by_id:
                by_id[listing_id] = listing
                file_new += 1
                continue

            duplicates += 1
            file_duplicates += 1
            changes = _meaningful_changes(by_id[listing_id], listing)
            if changes:
                duplicate_conflicts.append(
                    {
                        "listing_id": listing_id,
                        "kept_source_file": by_id[listing_id].get("source_file"),
                        "conflicting_source_file": path.name,
                        "changes": changes,
                    }
                )

        per_file.append(
            {
                "file": path.name,
                "parsed": len(listings),
                "new_unique": file_new,
                "duplicates": file_duplicates,
            }
        )

    return list(by_id.values()), {
        "parsed_cards": parsed_cards,
        "unique_observed": len(by_id),
        "duplicates": duplicates,
        "duplicate_conflicts": duplicate_conflicts,
        "per_file": per_file,
    }


def apply_update(
    current_state: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    observed_at: str,
    *,
    full_snapshot: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge one observation batch into canonical state.

    Incremental mode never interprets absence as removal. Full-snapshot mode
    marks previously active records missing from the observation as inactive;
    records are never deleted, so the operation remains reversible/auditable.
    """

    state_by_id: dict[str, dict[str, Any]] = {
        item["listing_id"]: dict(item)
        for item in current_state
        if item.get("listing_id")
    }
    original_order = [
        item["listing_id"]
        for item in current_state
        if item.get("listing_id")
    ]

    observed_ids: set[str] = set()
    new_ids: list[str] = []
    updated: list[dict[str, Any]] = []
    unchanged_ids: list[str] = []
    reactivated_ids: list[str] = []

    for fresh in observed:
        listing_id = fresh["listing_id"]
        observed_ids.add(listing_id)
        old = state_by_id.get(listing_id)

        if old is None:
            record = dict(fresh)
            record["first_seen_at"] = observed_at
            record["last_seen_at"] = observed_at
            record["last_changed_at"] = observed_at
            record["baseline"] = False
            record["is_active"] = True
            record["inactive_since"] = None
            state_by_id[listing_id] = record
            original_order.append(listing_id)
            new_ids.append(listing_id)
            continue

        changes = _meaningful_changes(old, fresh)
        was_active = old.get("is_active", True) is not False
        record = dict(old)

        for field in REFRESH_FIELDS:
            if field in fresh:
                record[field] = fresh[field]

        record["last_seen_at"] = observed_at
        record["is_active"] = True
        record["inactive_since"] = None
        record.setdefault("first_seen_at", observed_at)
        record.setdefault("baseline", False)

        if not was_active:
            reactivated_ids.append(listing_id)

        if changes or not was_active:
            record["last_changed_at"] = observed_at
            updated.append(
                {
                    "listing_id": listing_id,
                    "reactivated": not was_active,
                    "changes": changes,
                }
            )
        else:
            unchanged_ids.append(listing_id)

        state_by_id[listing_id] = record

    removed_ids: list[str] = []
    if full_snapshot:
        for listing_id, record in state_by_id.items():
            if listing_id in observed_ids:
                continue
            if record.get("is_active", True) is False:
                continue
            record["is_active"] = False
            record["inactive_since"] = observed_at
            record["last_changed_at"] = observed_at
            removed_ids.append(listing_id)

    state = [state_by_id[listing_id] for listing_id in original_order]

    summary = {
        "mode": "full_snapshot" if full_snapshot else "incremental",
        "observed_at": observed_at,
        "state_before": len(current_state),
        "state_after": len(state),
        "observed_unique": len(observed_ids),
        "new": len(new_ids),
        "updated": len(updated),
        "unchanged": len(unchanged_ids),
        "reactivated": len(reactivated_ids),
        "marked_inactive": len(removed_ids),
        "new_ids": new_ids,
        "updated_listings": updated,
        "unchanged_ids": unchanged_ids,
        "reactivated_ids": reactivated_ids,
        "marked_inactive_ids": removed_ids,
    }
    return state, summary


def _archive_state(state_path: Path, history_dir: Path, stamp: str) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_path = history_dir / f"aruodas_current_state_{stamp}.json"
    counter = 2
    while archive_path.exists():
        archive_path = history_dir / f"aruodas_current_state_{stamp}_{counter}.json"
        counter += 1
    shutil.copy2(state_path, archive_path)
    return archive_path


def _move_processed(paths: list[Path], processed_dir: Path, stamp: str) -> list[str]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    destinations: list[str] = []

    for source in paths:
        destination = processed_dir / f"{stamp}__{source.name}"
        counter = 2
        while destination.exists():
            destination = processed_dir / f"{stamp}__{counter}__{source.name}"
            counter += 1
        shutil.move(str(source), str(destination))
        destinations.append(str(destination))

    return destinations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge manually saved Aruodas result pages into canonical current state."
    )
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help=(
            "incremental: absence never means removal; full: missing active "
            "listings are marked inactive (never deleted)"
        ),
    )
    parser.add_argument(
        "--keep-inputs",
        action="store_true",
        help="Do not move successfully processed HTML files out of the inbox.",
    )
    args = parser.parse_args()

    if not args.state.exists():
        raise FileNotFoundError(f"Current state not found: {args.state}")

    args.inbox.mkdir(parents=True, exist_ok=True)
    input_paths = sorted(args.inbox.glob("*.html"))
    if not input_paths:
        raise FileNotFoundError(
            f"No .html files found in {args.inbox}. Save Aruodas search-result pages there first."
        )

    current_state = json.loads(args.state.read_text(encoding="utf-8"))
    observed, parse_summary = parse_inbox(input_paths)
    if not observed:
        raise RuntimeError("Input pages parsed successfully but contained zero Aruodas listings.")

    observed_at = _utc_now()
    stamp = _stamp(observed_at)
    full_snapshot = args.mode == "full"

    next_state, update_summary = apply_update(
        current_state,
        observed,
        observed_at,
        full_snapshot=full_snapshot,
    )

    archive_path = _archive_state(args.state, args.history_dir, stamp)
    _write_json_atomic(args.state, next_state)

    report = {
        "update_version": UPDATE_VERSION,
        "run_at": observed_at,
        "mode": update_summary["mode"],
        "input_files": [path.name for path in input_paths],
        "parse": parse_summary,
        "update": update_summary,
        "state_archive": str(archive_path),
        "processed_files": [],
    }

    report_path = args.report_dir / f"aruodas_update_{stamp}.json"
    _write_json_atomic(report_path, report)

    processed_files: list[str] = []
    if not args.keep_inputs:
        processed_files = _move_processed(input_paths, args.processed, stamp)
        report["processed_files"] = processed_files
        _write_json_atomic(report_path, report)

    print()
    print("=== ARUODAS STATE UPDATE ===")
    print(f"Version:                  {UPDATE_VERSION}")
    print(f"Mode:                     {update_summary['mode']}")
    print(f"Input pages:              {len(input_paths)}")
    print(f"Cards parsed:             {parse_summary['parsed_cards']}")
    print(f"Unique observed:          {parse_summary['unique_observed']}")
    print(f"Input duplicates:         {parse_summary['duplicates']}")
    print(f"Duplicate conflicts:      {len(parse_summary['duplicate_conflicts'])}")
    print(f"NEW:                      {update_summary['new']}")
    print(f"UPDATED:                  {update_summary['updated']}")
    print(f"UNCHANGED:                {update_summary['unchanged']}")
    print(f"REACTIVATED:              {update_summary['reactivated']}")
    print(f"MARKED INACTIVE:          {update_summary['marked_inactive']}")
    print(f"State rows:               {update_summary['state_after']}")
    print(f"State:                    {args.state}")
    print(f"Backup:                   {archive_path}")
    print(f"Report:                   {report_path}")
    if args.keep_inputs:
        print("Inputs:                   kept in inbox (--keep-inputs)")
    else:
        print(f"Moved to processed:       {len(processed_files)}")

    if full_snapshot:
        print()
        print("Full-snapshot semantics: missing active listings were marked inactive, not deleted.")
    else:
        print()
        print("Incremental semantics: absence from these pages did NOT imply removal.")

    if update_summary["new_ids"]:
        print()
        print("=== NEW LISTINGS ===")
        for listing_id in update_summary["new_ids"]:
            item = next(item for item in next_state if item["listing_id"] == listing_id)
            print(
                f"{listing_id} | {item.get('district') or '-'} | "
                f"{item.get('street') or '-'} | {item.get('rooms') or '-'}r | "
                f"{item.get('area_m2') or '-'} m² | {item.get('rent_eur') or '-'} €"
            )

    if update_summary["updated_listings"]:
        print()
        print("=== UPDATED LISTINGS ===")
        for item in update_summary["updated_listings"]:
            fields = ", ".join(item["changes"].keys()) or "reactivated"
            print(f"{item['listing_id']} | changed: {fields}")


if __name__ == "__main__":
    main()
