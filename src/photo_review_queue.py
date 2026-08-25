from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT = Path("data/parsed/aruodas_candidates_text_enriched.json")
DEFAULT_OUTPUT_DIR = Path("data/photos/review_queue")
DEFAULT_ZIP = Path("data/photos/aruodas_photo_review_queue.zip")
DEFAULT_LIMIT = 20
DEFAULT_IMAGES_PER_LISTING = 4
DEFAULT_EXTRA_IDS = ("4-1492279",)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151 Safari/537.36"
    )
}


def load_candidates(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Candidate file must contain a JSON list: {path}")
    return data


def select_candidates(
    candidates: list[dict[str, Any]],
    limit: int,
    extra_ids: tuple[str, ...] = DEFAULT_EXTRA_IDS,
) -> list[dict[str, Any]]:
    survivors = [
        item
        for item in candidates
        if item.get("candidate_tier") != "REJECT"
        and not item.get("candidate_hard_reject")
        and item.get("is_active", True) is not False
    ]

    selected = survivors[:limit]
    selected_ids = {item.get("listing_id") for item in selected}
    by_id = {
        item.get("listing_id"): item
        for item in survivors
        if item.get("listing_id")
    }

    for listing_id in extra_ids:
        if listing_id not in selected_ids and listing_id in by_id:
            selected.append(by_id[listing_id])
            selected_ids.add(listing_id)

    return selected


def extension_from_response(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def download_candidate(
    candidate: dict[str, Any],
    output_dir: Path,
    images_per_listing: int,
) -> dict[str, Any]:
    listing_id = str(candidate["listing_id"])
    listing_dir = output_dir / listing_id
    listing_dir.mkdir(parents=True, exist_ok=True)

    urls = list(candidate.get("image_urls") or [])[:images_per_listing]
    downloaded_files: list[str] = []
    failures: list[dict[str, str]] = []

    for index, url in enumerate(urls, start=1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            extension = extension_from_response(response)
            path = listing_dir / f"photo_{index:02d}{extension}"
            path.write_bytes(response.content)
            downloaded_files.append(str(path.relative_to(output_dir)))
        except requests.RequestException as exc:
            failures.append({"url": str(url), "error": str(exc)})

    listing_manifest = {
        "listing_id": listing_id,
        "url": candidate.get("url"),
        "district": candidate.get("district"),
        "street": candidate.get("street"),
        "rooms": candidate.get("rooms"),
        "area_m2": candidate.get("area_m2"),
        "rent_eur": candidate.get("rent_eur"),
        "aruodas_candidate_score": candidate.get("aruodas_candidate_score"),
        "candidate_tier": candidate.get("candidate_tier"),
        "location_zone": candidate.get("location_zone"),
        "location_score": candidate.get("location_score"),
        "text_enrichment_status": candidate.get("text_enrichment_status"),
        "text_enrichment": candidate.get("text_enrichment"),
        "requested_image_count": len(urls),
        "downloaded_image_count": len(downloaded_files),
        "downloaded_files": downloaded_files,
        "failures": failures,
    }

    (listing_dir / "listing.json").write_text(
        json.dumps(listing_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return listing_manifest


def zip_queue(output_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir.parent))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download preview photos for the strongest current Aruodas candidates "
            "and package them into one ZIP for visual review."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--images-per-listing",
        type=int,
        default=DEFAULT_IMAGES_PER_LISTING,
    )
    parser.add_argument(
        "--no-extra-control",
        action="store_true",
        help="Do not append the known 4-1492279 visual-control listing.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Candidate file not found: {args.input}")
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if args.images_per_listing < 1:
        raise ValueError("--images-per-listing must be at least 1")

    candidates = load_candidates(args.input)
    extra_ids = () if args.no_extra_control else DEFAULT_EXTRA_IDS
    selected = select_candidates(candidates, args.limit, extra_ids)

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    print()
    print("=== ARUODAS PHOTO REVIEW QUEUE ===")
    print(f"Candidates selected:       {len(selected)}")
    print(f"Images per listing:        {args.images_per_listing}")

    for index, candidate in enumerate(selected, start=1):
        listing_id = candidate.get("listing_id") or "unknown"
        print(
            f"[{index:02d}/{len(selected):02d}] {listing_id} | "
            f"{candidate.get('street') or '-'} | "
            f"{candidate.get('rent_eur') or '-'} €"
        )
        record = download_candidate(
            candidate,
            args.output_dir,
            args.images_per_listing,
        )
        print(
            f"       downloaded "
            f"{record['downloaded_image_count']}/{record['requested_image_count']}"
        )
        manifest.append(record)

    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    zip_queue(args.output_dir, args.zip)

    total_requested = sum(item["requested_image_count"] for item in manifest)
    total_downloaded = sum(item["downloaded_image_count"] for item in manifest)
    listings_with_images = sum(
        1 for item in manifest if item["downloaded_image_count"] > 0
    )

    print()
    print("=== REVIEW PACKAGE READY ===")
    print(f"Listings with photos:      {listings_with_images}/{len(manifest)}")
    print(f"Photos downloaded:         {total_downloaded}/{total_requested}")
    print(f"Folder:                    {args.output_dir}")
    print(f"ZIP:                       {args.zip}")


if __name__ == "__main__":
    main()
