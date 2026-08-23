from __future__ import annotations

import json
from pathlib import Path

import requests


STATE_FILE = Path("data/parsed/aruodas_current_state.json")

TEST_LISTING_ID = "4-1025447"

OUTPUT_DIR = Path("data/photos/test")


def load_listing(listing_id: str) -> dict:

    listings = json.loads(
        STATE_FILE.read_text(
            encoding="utf-8"
        )
    )

    for listing in listings:

        if listing.get("listing_id") == listing_id:
            return listing

    raise ValueError(
        f"Listing not found: {listing_id}"
    )


def main():

    listing = load_listing(
        TEST_LISTING_ID
    )

    urls = listing.get(
        "image_urls",
        []
    )

    if not urls:
        raise RuntimeError(
            "Listing has no image URLs."
        )

    listing_dir = (
        OUTPUT_DIR
        / TEST_LISTING_ID
    )

    listing_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 70)
    print("ARUODAS PHOTO DOWNLOAD TEST")
    print("=" * 70)

    print(
        f"Listing: {listing['listing_id']}"
    )

    print(
        f"{listing['district']}, "
        f"{listing['street']}"
    )

    print(
        f"Rent: {listing['rent_eur']} €"
    )

    print(
        f"Images: {len(urls)}"
    )

    print()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151 Safari/537.36"
        )
    }

    downloaded = 0

    for index, url in enumerate(
        urls,
        start=1,
    ):

        print(
            f"Downloading image {index}/{len(urls)}..."
        )

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=20,
            )

            response.raise_for_status()

        except requests.RequestException as exc:

            print(
                f"FAILED: {exc}"
            )

            continue

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if "jpeg" in content_type:
            extension = ".jpg"

        elif "png" in content_type:
            extension = ".png"

        elif "webp" in content_type:
            extension = ".webp"

        else:
            extension = ".jpg"

        output_path = (
            listing_dir
            / f"photo_{index:02d}{extension}"
        )

        output_path.write_bytes(
            response.content
        )

        size_kb = (
            len(response.content)
            / 1024
        )

        print(
            f"OK: {output_path} "
            f"({size_kb:.1f} KB)"
        )

        downloaded += 1

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)

    print(
        f"Downloaded: {downloaded}/{len(urls)}"
    )

    print(
        f"Folder: {listing_dir}"
    )


if __name__ == "__main__":
    main()