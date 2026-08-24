from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.candidates import score_listing


DEFAULT_STATE = Path("data/parsed/aruodas_current_state.json")
DEFAULT_REPORT_DIR = Path("data/parsed/update_reports")
DEFAULT_OUTPUT = Path("data/parsed/aruodas_latest_update_candidates.json")
TRIAGE_VERSION = "aruodas-update-triage-v1"


def latest_report(report_dir: Path) -> Path:
    reports = sorted(report_dir.glob("aruodas_update_*.json"))
    if not reports:
        raise FileNotFoundError(f"No update reports found in {report_dir}")
    return reports[-1]


def build_update_triage(
    state: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Score only listings touched by one update run.

    This is a fast post-update triage step. It does not pretend that every
    listing has precise coordinates or text enrichment; those expensive steps
    happen only for the most interesting new/changed listings.
    """

    update = report.get("update") or {}
    new_ids = set(update.get("new_ids") or [])
    updated_rows = update.get("updated_listings") or []
    updated_by_id = {
        row.get("listing_id"): row
        for row in updated_rows
        if row.get("listing_id")
    }
    touched_ids = new_ids | set(updated_by_id)

    by_id = {
        item.get("listing_id"): item
        for item in state
        if item.get("listing_id")
    }

    triage: list[dict[str, Any]] = []
    for listing_id in touched_ids:
        source = by_id.get(listing_id)
        if source is None:
            continue

        scored = score_listing(source)
        scored["update_event"] = "NEW" if listing_id in new_ids else "UPDATED"
        scored["update_changes"] = (
            updated_by_id.get(listing_id, {}).get("changes") or {}
        )
        scored["update_reactivated"] = bool(
            updated_by_id.get(listing_id, {}).get("reactivated")
        )
        scored["update_triage_version"] = TRIAGE_VERSION
        triage.append(scored)

    triage.sort(
        key=lambda item: (
            1 if item["update_event"] == "NEW" else 0,
            item.get("candidate_priority") or 0,
            item.get("aruodas_candidate_score") or 0,
            -(float(item.get("rent_eur") or 10_000)),
        ),
        reverse=True,
    )
    return triage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank NEW/UPDATED listings from the latest Aruodas state update."
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report_path = args.report or latest_report(args.report_dir)
    if not args.state.exists():
        raise FileNotFoundError(f"Current state not found: {args.state}")
    if not report_path.exists():
        raise FileNotFoundError(f"Update report not found: {report_path}")

    state = json.loads(args.state.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    triage = build_update_triage(state, report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(triage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    new_count = sum(1 for item in triage if item["update_event"] == "NEW")
    updated_count = sum(1 for item in triage if item["update_event"] == "UPDATED")
    actionable = sum(
        1
        for item in triage
        if item["candidate_tier"] in {"HIGH", "PROMISING"}
        and not item.get("candidate_hard_reject")
    )

    print()
    print("=== LATEST UPDATE CANDIDATE TRIAGE ===")
    print(f"Version:                  {TRIAGE_VERSION}")
    print(f"Report:                   {report_path}")
    print(f"Touched listings:         {len(triage)}")
    print(f"NEW:                      {new_count}")
    print(f"UPDATED:                  {updated_count}")
    print(f"HIGH/PROMISING:           {actionable}")
    print(f"Output:                   {args.output}")

    print()
    for item in triage:
        changes = ",".join(item.get("update_changes", {}).keys()) or "-"
        print(
            f"{item['update_event']:<7} | {item['listing_id']} | "
            f"{item.get('aruodas_candidate_score', 0):>5.1f} | "
            f"{item.get('candidate_tier', '-'):<9} | "
            f"{item.get('district') or '-'} | {item.get('street') or '-'} | "
            f"{item.get('rooms') or '-'}r | {item.get('area_m2') or '-'} m² | "
            f"{item.get('rent_eur') or '-'} € | changes={changes}"
        )


if __name__ == "__main__":
    main()
