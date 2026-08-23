from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE_URL = "https://www.aruodas.lt/butu-nuoma/kaune/"
LISTING_SELECTOR = "div.list-row-v2.object-row.srentflat.advert"

RAW_DIR = Path("data/raw/browser")
PROFILE_DIR = Path(".playwright-profile")

MAX_PAGES = 3


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL

    return f"https://www.aruodas.lt/butu-nuoma/kaune/puslapis/{page_number}/"


def challenge_detected(page) -> bool:
    url = page.url.lower()

    if "__cf_chl" in url:
        return True

    text = page.locator("body").inner_text().lower()

    indicators = [
        "verify you are human",
        "patvirtinkite, kad esate žmogus",
        "checking your browser",
        "cloudflare",
    ]

    return any(x in text for x in indicators)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            locale="lt-LT",
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = context.pages[0] if context.pages else context.new_page()

        collected = 0

        for page_number in range(1, MAX_PAGES + 1):

            url = page_url(page_number)

            print()
            print("=" * 70)
            print(f"PAGE {page_number}")
            print("=" * 70)
            print(f"Opening: {url}")

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=45_000,
            )

            page.wait_for_timeout(3000)

            status = response.status if response else None

            print(f"HTTP: {status}")
            print(f"URL:  {page.url}")
            print(f"Title: {page.title()}")

            if challenge_detected(page):

                print()
                print("[CLOUDFLARE CHALLENGE]")
                print(
                    "Complete the human verification manually "
                    "in the open browser."
                )

                input(
                    "After the actual listings are visible, "
                    "press ENTER here..."
                )

                page.wait_for_timeout(2000)

            try:
                page.wait_for_selector(
                    LISTING_SELECTOR,
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:

                print()
                print("[FAILED] Listing cards still not available.")
                break

            listing_count = page.locator(
                LISTING_SELECTOR
            ).count()

            print(f"Listings found: {listing_count}")

            if listing_count == 0:
                print("[FAILED] No listings.")
                break

            timestamp = datetime.now(
                timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")

            html_path = RAW_DIR / (
                f"kaunas_page_{page_number}_{timestamp}.html"
            )

            html_path.write_text(
                page.content(),
                encoding="utf-8",
            )

            print(f"Saved: {html_path}")

            collected += listing_count

            # Small normal pause between page navigations.
            page.wait_for_timeout(2500)

        print()
        print("=" * 70)
        print("DONE")
        print("=" * 70)
        print(f"Listings encountered: {collected}")

        context.close()


if __name__ == "__main__":
    main()