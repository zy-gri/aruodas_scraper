import unittest

from src.text_enrichment import apply_text_enrichment, merge_text_enrichment


class TextEnrichmentTests(unittest.TestCase):
    def _candidate(self):
        return {
            "listing_id": "4-1",
            "rent_eur": 650.0,
            "rooms": 2,
            "area_m2": 40.0,
            "candidate_tier": "HIGH",
            "candidate_priority": 4,
            "candidate_hard_reject": False,
            "candidate_reject_reasons": [],
            "aruodas_candidate_score": 88.0,
        }

    def test_room_rental_becomes_hard_reject(self):
        result = apply_text_enrichment(
            self._candidate(),
            {"listing_scope": "room_rental"},
        )

        self.assertTrue(result["candidate_hard_reject"])
        self.assertEqual(result["candidate_tier"], "REJECT")
        self.assertEqual(result["candidate_priority"], 0)
        self.assertEqual(result["post_enrichment_status"], "REJECT")

    def test_no_window_becomes_hard_reject(self):
        result = apply_text_enrichment(
            self._candidate(),
            {
                "listing_scope": "whole_apartment",
                "basement_or_semi_basement": True,
                "no_window": True,
            },
        )

        self.assertTrue(result["candidate_hard_reject"])
        self.assertIn("no window", " ".join(result["candidate_reject_reasons"]).lower())

    def test_semi_basement_alone_is_not_automatic_reject(self):
        result = apply_text_enrichment(
            self._candidate(),
            {
                "listing_scope": "whole_apartment",
                "basement_or_semi_basement": True,
                "no_window": False,
            },
        )

        self.assertFalse(result["candidate_hard_reject"])
        self.assertEqual(result["post_enrichment_status"], "SURVIVOR")

    def test_dynamic_search_index_fields_are_not_allowed_to_overwrite_baseline(self):
        result = apply_text_enrichment(
            self._candidate(),
            {
                "listing_scope": "whole_apartment",
                "rent_eur": 999.0,
                "rooms": 9,
                "area_m2": 999,
                "description_summary": "Good apartment.",
            },
        )

        self.assertEqual(result["rent_eur"], 650.0)
        self.assertEqual(result["rooms"], 2)
        self.assertEqual(result["area_m2"], 40.0)
        self.assertNotIn("rent_eur", result["text_enrichment"])
        self.assertNotIn("rooms", result["text_enrichment"])

    def test_missing_enrichment_leaves_candidate_unmodified(self):
        candidate = self._candidate()
        result = apply_text_enrichment(candidate, None)

        self.assertEqual(result["candidate_tier"], "HIGH")
        self.assertEqual(result["text_enrichment_status"], "missing")

    def test_merge_matches_by_listing_id(self):
        candidates = [self._candidate()]
        enrichments = [
            {
                "listing_id": "4-1",
                "listing_scope": "whole_apartment",
                "dishwasher": True,
            }
        ]

        result = merge_text_enrichment(candidates, enrichments)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["text_enrichment"]["dishwasher"])
        self.assertEqual(result[0]["post_enrichment_status"], "SURVIVOR")


if __name__ == "__main__":
    unittest.main()
