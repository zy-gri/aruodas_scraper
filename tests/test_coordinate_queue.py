import unittest

from src.coordinate_queue import (
    build_coordinate_queue,
    coordinate_priority,
    is_coordinate_candidate,
)


class CoordinateQueueTests(unittest.TestCase):
    def _item(self, listing_id="4-1", score=90.0):
        return {
            "listing_id": listing_id,
            "url": f"https://www.aruodas.lt/{listing_id}",
            "district": "Centras",
            "street": "Laisvės al.",
            "rent_eur": 600.0,
            "rooms": 2,
            "area_m2": 40.0,
            "aruodas_candidate_score": score,
            "candidate_tier": "HIGH",
            "candidate_hard_reject": False,
            "post_enrichment_status": "SURVIVOR",
            "text_enrichment_status": "enriched",
            "text_enrichment": {
                "listing_scope": "whole_apartment",
                "description_summary": "Good central apartment.",
            },
        }

    def test_rejected_listing_is_not_eligible(self):
        item = self._item()
        item["candidate_hard_reject"] = True
        item["candidate_tier"] = "REJECT"
        item["post_enrichment_status"] = "REJECT"
        self.assertFalse(is_coordinate_candidate(item))

    def test_missing_text_enrichment_is_not_eligible(self):
        item = self._item()
        item["text_enrichment_status"] = "missing"
        self.assertFalse(is_coordinate_candidate(item))

    def test_existing_coordinates_are_not_queued_again(self):
        item = self._item()
        item["coordinates_found"] = True
        item["latitude"] = 54.9
        item["longitude"] = 23.9
        self.assertFalse(is_coordinate_candidate(item))

    def test_quality_features_raise_manual_priority(self):
        plain = self._item("plain")
        strong = self._item("strong")
        strong["text_enrichment"].update(
            {
                "parking": True,
                "air_conditioning": True,
                "dishwasher": True,
                "high_ceilings": True,
            }
        )
        self.assertGreater(
            coordinate_priority(strong)["coordinate_queue_score"],
            coordinate_priority(plain)["coordinate_queue_score"],
        )

    def test_basement_is_heavily_deprioritized_not_deleted(self):
        item = self._item()
        item["text_enrichment"]["basement_or_semi_basement"] = True
        result = coordinate_priority(item)
        self.assertTrue(is_coordinate_candidate(item))
        self.assertLess(result["coordinate_queue_adjustment"], -10)
        self.assertIn("basement_or_semi_basement", result["coordinate_queue_concerns"])

    def test_queue_respects_priority_and_limit(self):
        weak = self._item("weak", 88.0)
        strong = self._item("strong", 89.0)
        strongest = self._item("strongest", 90.0)
        strongest["text_enrichment"]["parking"] = True
        strongest["text_enrichment"]["air_conditioning"] = True

        queue = build_coordinate_queue([weak, strong, strongest], limit=2)

        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["listing_id"], "strongest")
        self.assertEqual(queue[1]["listing_id"], "strong")
        self.assertEqual(queue[0]["save_as"], "data/raw/detail_strongest.html")


if __name__ == "__main__":
    unittest.main()
