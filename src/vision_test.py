from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


STATE_FILE = Path("data/parsed/aruodas_current_state.json")

# Known listing from our baseline.
TEST_LISTING_ID = "4-1025447"

# Cheap model for repeated visual screening.
MODEL = "gpt-5.6-luna"


def load_listing(listing_id: str) -> dict:
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f"State file not found: {STATE_FILE}"
        )

    listings = json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    )

    for listing in listings:
        if listing.get("listing_id") == listing_id:
            return listing

    raise ValueError(
        f"Listing {listing_id} not found in {STATE_FILE}"
    )


def main():

    print()
    print("=" * 70)
    print("ARUODAS VISION URL TEST")
    print("=" * 70)

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY was not found in .env"
        )

    client = OpenAI(
        api_key=api_key
    )

    listing = load_listing(
        TEST_LISTING_ID
    )

    image_urls = listing.get(
        "image_urls",
        []
    )

    if not image_urls:
        raise RuntimeError(
            "Listing has no image_urls."
        )

    print()
    print(f"Listing:  {listing['listing_id']}")
    print(
        f"Location: {listing['district']}, "
        f"{listing['street']}"
    )
    print(
        f"Rent:     {listing['rent_eur']:.0f} €"
    )
    print(
        f"Rooms:    {listing['rooms']}"
    )
    print(
        f"Area:     {listing['area_m2']} m²"
    )

    print()
    print(f"Images: {len(image_urls)}")

    for i, url in enumerate(
        image_urls,
        start=1,
    ):
        print(f"{i}. {url}")

    prompt = f"""
You are evaluating a rental apartment for possible
short-term-rental / Airbnb arbitrage.

Listing information:
- City: {listing.get("city")}
- District: {listing.get("district")}
- Street: {listing.get("street")}
- Monthly rent: {listing.get("rent_eur")} EUR
- Rooms: {listing.get("rooms")}
- Area: {listing.get("area_m2")} m2
- Year built: {listing.get("year_built")}
- Renovation year: {listing.get("renovation_year")}

Evaluate ONLY what can reasonably be inferred from the supplied photos.

We care heavily about whether the apartment visually looks attractive
enough for a short-term rental.

Look for:
- modern vs outdated / Soviet-style interior
- furniture quality
- kitchen quality
- bathroom quality if visible
- lighting
- natural brightness
- interior condition
- cleanliness
- visual consistency
- distinctive or premium features
- whether expensive renovation appears necessary
- whether the apartment could photograph well on Airbnb
- whether guests would perceive it as attractive

Do not assume rooms or features that are not visible.

Return ONLY valid JSON using this structure:

{{
  "interior_quality": 0.0,
  "airbnb_visual_appeal": 0.0,
  "modernity": 0.0,
  "furniture_quality": 0.0,
  "brightness": 0.0,
  "photo_presentation_quality": 0.0,
  "renovation_needed": true,
  "renovation_severity": "none|minor|moderate|major",
  "airbnb_ready": true,
  "visual_verdict": "REJECT|WEAK|POSSIBLE|PROMISING|EXCELLENT",
  "confidence": 0.0,
  "visible_strengths": [],
  "visible_weaknesses": [],
  "summary": ""
}}

Scores are from 0 to 10.
Confidence is from 0 to 1.
"""

    content = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]

    for url in image_urls:

        content.append(
            {
                "type": "input_image",
                "image_url": url,

                # Low is enough for this connectivity test
                # and is cheaper than high-detail analysis.
                "detail": "low",
            }
        )

    print()
    print("=" * 70)
    print("SENDING IMAGE URLS TO OPENAI")
    print("=" * 70)

    try:

        response = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
        )

    except Exception as exc:

        print()
        print("VISION TEST FAILED")
        print()
        print(type(exc).__name__)
        print(str(exc))

        print()
        print(
            "If the error specifically says an image URL "
            "could not be fetched/downloaded, then the "
            "Aruodas CDN does not allow direct API fetching."
        )

        return

    print()
    print("=" * 70)
    print("VISION RESULT")
    print("=" * 70)
    print()

    print(
        response.output_text
    )

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print(
        "The OpenAI API successfully received the "
        "Aruodas image URLs without us downloading them."
    )


if __name__ == "__main__":
    main()