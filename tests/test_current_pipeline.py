import unittest

from src.current_pipeline import active_records, build_current_views


class CurrentPipelineTests(unittest.TestCase):
    def _listing(self, listing_id="4-1", *, active=True):
        return {
            "listing_id": listing_id,
            "district": "Centras",
            "street": "Laisvės al.",
            "rooms": 2,
            "area_m2": 40.0,
            "rent_eur": 600.0,
            "year_built": 2020,
            "reserved": False,
            "is_active": active,
        }

    def test_inactive_records_are_excluded(self):
        items = [self._listing("active", active=True), self._listing("inactive", active=False)]
        result = active_records(items)
        self.assertEqual([item["listing_id"] for item in result], ["active"])

    def test_missing_is_active_defaults_to_active(self):
        item = self._listing()
        item.pop("is_active")
        self.assertEqual(len(active_records([item])), 1)

    def test_current_views_include_new_active_listing_and_apply_text_reject(self):
        whole = self._listing("whole")
        room = self._listing("room")
        enrichments = [
            {"listing_id": "whole", "listing_scope": "whole_apartment"},
            {"listing_id": "room", "listing_scope": "room_rental"},
        ]

        ranked, text_enriched = build_current_views([whole, room], enrichments)

        self.assertEqual(len(ranked), 2)
        by_id = {item["listing_id"]: item for item in text_enriched}
        self.assertEqual(by_id["whole"]["post_enrichment_status"], "SURVIVOR")
        self.assertEqual(by_id["room"]["candidate_tier"], "REJECT")


if __name__ == "__main__":
    unittest.main()
