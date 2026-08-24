import unittest

from src.update_triage import build_update_triage


class UpdateTriageTests(unittest.TestCase):
    def _state_item(self, listing_id, district="Centras", street="Laisvės al.", rent=600.0, reserved=False):
        return {
            "listing_id": listing_id,
            "district": district,
            "street": street,
            "rooms": 2,
            "area_m2": 45.0,
            "year_built": 2020,
            "rent_eur": rent,
            "reserved": reserved,
        }

    def test_only_new_and_updated_are_included(self):
        state = [
            self._state_item("new"),
            self._state_item("updated"),
            self._state_item("untouched"),
        ]
        report = {
            "update": {
                "new_ids": ["new"],
                "updated_listings": [
                    {"listing_id": "updated", "reactivated": False, "changes": {"rent_eur": {"old": 700, "new": 600}}}
                ],
            }
        }

        result = build_update_triage(state, report)
        ids = {item["listing_id"] for item in result}
        self.assertEqual(ids, {"new", "updated"})

    def test_new_listing_carries_new_event(self):
        state = [self._state_item("new")]
        report = {"update": {"new_ids": ["new"], "updated_listings": []}}

        result = build_update_triage(state, report)
        self.assertEqual(result[0]["update_event"], "NEW")
        self.assertEqual(result[0]["update_changes"], {})

    def test_updated_listing_keeps_change_details(self):
        state = [self._state_item("updated", rent=650.0)]
        report = {
            "update": {
                "new_ids": [],
                "updated_listings": [
                    {"listing_id": "updated", "reactivated": False, "changes": {"rent_eur": {"old": 700, "new": 650}}}
                ],
            }
        }

        result = build_update_triage(state, report)
        self.assertEqual(result[0]["update_event"], "UPDATED")
        self.assertIn("rent_eur", result[0]["update_changes"])

    def test_reserved_updated_listing_is_rejected_by_existing_scorer(self):
        state = [self._state_item("updated", reserved=True)]
        report = {
            "update": {
                "new_ids": [],
                "updated_listings": [
                    {"listing_id": "updated", "reactivated": False, "changes": {"reserved": {"old": False, "new": True}}}
                ],
            }
        }

        result = build_update_triage(state, report)
        self.assertEqual(result[0]["candidate_tier"], "REJECT")
        self.assertTrue(result[0]["candidate_hard_reject"])


if __name__ == "__main__":
    unittest.main()
