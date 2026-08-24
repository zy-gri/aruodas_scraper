import unittest

from src.repair_baseline import repair_dataset


class RepairBaselineTests(unittest.TestCase):
    def test_repair_preserves_metadata_and_replaces_search_fields(self):
        existing = [
            {
                "listing_id": "4-1082223",
                "heating": "Kaina padidėjusi 16,3%",
                "rent_eur": 698.0,
                "first_seen_at": "2026-08-23T10:00:00+00:00",
                "last_seen_at": "2026-08-23T10:00:00+00:00",
                "baseline": True,
                "location_zone": "LAISVES_CORE",
            }
        ]

        reparsed = {
            "4-1082223": {
                "listing_id": "4-1082223",
                "source": "aruodas",
                "url": "https://www.aruodas.lt/4-1082223/",
                "city": "Kaunas",
                "district": "Centras",
                "street": "Laisvės al.",
                "listed_age_text": "Prieš 1 d.",
                "rooms": 2,
                "area_m2": 45.0,
                "floor": 2,
                "floors_total": 4,
                "year_built": 1930,
                "renovation_year": None,
                "heating": "Centrinis",
                "rent_eur": 698.0,
                "price_per_m2": 15.51,
                "price_reduction_pct": None,
                "reserved": False,
                "pets_allowed": False,
                "main_image_url": "https://example.com/main.jpg",
                "extra_image_urls": [],
                "image_urls": ["https://example.com/main.jpg"],
                "preview_image_count": 1,
                "raw_text": "example",
                "source_file": "centras_1.html",
            }
        }

        repaired, changed_fields, changed_listings = repair_dataset(existing, reparsed)
        row = repaired[0]

        self.assertEqual(changed_listings, 1)
        self.assertEqual(row["heating"], "Centrinis")
        self.assertEqual(changed_fields["heating"], 1)

        self.assertEqual(row["first_seen_at"], "2026-08-23T10:00:00+00:00")
        self.assertEqual(row["last_seen_at"], "2026-08-23T10:00:00+00:00")
        self.assertTrue(row["baseline"])
        self.assertEqual(row["location_zone"], "LAISVES_CORE")

    def test_repair_refuses_listing_id_mismatch(self):
        existing = [{"listing_id": "4-1"}]
        reparsed = {"4-2": {"listing_id": "4-2"}}

        with self.assertRaises(RuntimeError):
            repair_dataset(existing, reparsed)


if __name__ == "__main__":
    unittest.main()
