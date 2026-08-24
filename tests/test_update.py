import unittest

from src.update import apply_update


class UpdateTests(unittest.TestCase):
    def _existing(self, listing_id="4-1", rent=600.0):
        return {
            "source": "aruodas",
            "listing_id": listing_id,
            "url": f"https://www.aruodas.lt/{listing_id}",
            "city": "Kaunas",
            "district": "Centras",
            "street": "Laisvės al.",
            "rooms": 2,
            "area_m2": 40.0,
            "floor": 2,
            "floors_total": 4,
            "year_built": 1930,
            "renovation_year": 2020,
            "heating": "Centrinis",
            "rent_eur": rent,
            "price_per_m2": rent / 40.0,
            "price_reduction_pct": None,
            "reserved": False,
            "pets_allowed": False,
            "preview_image_count": 4,
            "first_seen_at": "2026-08-23T18:00:00+00:00",
            "last_seen_at": "2026-08-23T18:00:00+00:00",
            "baseline": True,
            "custom_enrichment": "preserve-me",
        }

    def _fresh(self, listing_id="4-1", rent=600.0):
        item = self._existing(listing_id, rent)
        for key in ("first_seen_at", "last_seen_at", "baseline", "custom_enrichment"):
            item.pop(key, None)
        item["listed_age_text"] = "Prieš 1 val."
        item["raw_text"] = "fresh"
        item["source_file"] = "page.html"
        return item

    def test_incremental_absence_never_marks_missing_listing_inactive(self):
        current = [self._existing("4-1"), self._existing("4-2")]
        observed = [self._fresh("4-1")]

        state, summary = apply_update(
            current,
            observed,
            "2026-08-24T20:00:00+00:00",
            full_snapshot=False,
        )

        second = next(item for item in state if item["listing_id"] == "4-2")
        self.assertNotEqual(second.get("is_active"), False)
        self.assertEqual(summary["marked_inactive"], 0)

    def test_full_snapshot_marks_missing_active_listing_inactive_not_deleted(self):
        current = [self._existing("4-1"), self._existing("4-2")]
        observed = [self._fresh("4-1")]

        state, summary = apply_update(
            current,
            observed,
            "2026-08-24T20:00:00+00:00",
            full_snapshot=True,
        )

        self.assertEqual(len(state), 2)
        second = next(item for item in state if item["listing_id"] == "4-2")
        self.assertFalse(second["is_active"])
        self.assertEqual(second["inactive_since"], "2026-08-24T20:00:00+00:00")
        self.assertEqual(summary["marked_inactive_ids"], ["4-2"])

    def test_new_listing_gets_first_and_last_seen_metadata(self):
        state, summary = apply_update(
            [],
            [self._fresh("4-new", 500.0)],
            "2026-08-24T20:00:00+00:00",
        )

        self.assertEqual(summary["new"], 1)
        self.assertEqual(state[0]["first_seen_at"], "2026-08-24T20:00:00+00:00")
        self.assertEqual(state[0]["last_seen_at"], "2026-08-24T20:00:00+00:00")
        self.assertFalse(state[0]["baseline"])
        self.assertTrue(state[0]["is_active"])

    def test_price_change_is_updated_and_first_seen_is_preserved(self):
        current = [self._existing("4-1", 600.0)]
        observed = [self._fresh("4-1", 550.0)]

        state, summary = apply_update(
            current,
            observed,
            "2026-08-24T20:00:00+00:00",
        )

        self.assertEqual(summary["updated"], 1)
        self.assertIn("rent_eur", summary["updated_listings"][0]["changes"])
        self.assertEqual(state[0]["rent_eur"], 550.0)
        self.assertEqual(state[0]["first_seen_at"], "2026-08-23T18:00:00+00:00")
        self.assertEqual(state[0]["custom_enrichment"], "preserve-me")

    def test_age_text_churn_does_not_count_as_meaningful_update(self):
        current = [self._existing("4-1", 600.0)]
        current[0]["listed_age_text"] = "Prieš 1 d."
        observed = [self._fresh("4-1", 600.0)]
        observed[0]["listed_age_text"] = "Prieš 2 d."

        state, summary = apply_update(
            current,
            observed,
            "2026-08-24T20:00:00+00:00",
        )

        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(state[0]["listed_age_text"], "Prieš 2 d.")
        self.assertEqual(state[0]["last_seen_at"], "2026-08-24T20:00:00+00:00")

    def test_inactive_listing_reappearing_is_reactivated(self):
        current = [self._existing("4-1")]
        current[0]["is_active"] = False
        current[0]["inactive_since"] = "2026-08-24T10:00:00+00:00"

        state, summary = apply_update(
            current,
            [self._fresh("4-1")],
            "2026-08-24T20:00:00+00:00",
        )

        self.assertTrue(state[0]["is_active"])
        self.assertIsNone(state[0]["inactive_since"])
        self.assertEqual(summary["reactivated"], 1)
        self.assertEqual(summary["updated"], 1)


if __name__ == "__main__":
    unittest.main()
