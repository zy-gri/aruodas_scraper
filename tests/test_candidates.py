import unittest

from src.candidates import rank_listings, score_listing


class CandidateScorerTests(unittest.TestCase):
    def test_reserved_listing_is_hard_reject(self):
        listing = {
            "listing_id": "4-1",
            "district": "Centras",
            "street": "Laisvės al.",
            "rooms": 2,
            "area_m2": 45,
            "rent_eur": 500,
            "year_built": 2020,
            "reserved": True,
        }

        result = score_listing(listing)

        self.assertTrue(result["candidate_hard_reject"])
        self.assertEqual(result["candidate_tier"], "REJECT")
        self.assertEqual(result["candidate_priority"], 0)

    def test_exact_micro_location_beats_district_proxy(self):
        listing = {
            "listing_id": "4-2",
            "district": "Vilijampolė",
            "street": "Brastos g.",
            "rooms": 2,
            "area_m2": 48,
            "rent_eur": 650,
            "year_built": 2021,
            "reserved": False,
            "location_zone": "PILIAMIESTIS",
            "location_score": 92,
        }

        result = score_listing(listing)

        self.assertEqual(result["candidate_location_source"], "coordinates")
        self.assertFalse(result["needs_coordinate_enrichment"])
        self.assertAlmostEqual(
            result["candidate_score_components"]["location"],
            32.2,
            places=1,
        )

    def test_brastos_without_coordinates_is_only_a_proxy(self):
        listing = {
            "listing_id": "4-3",
            "district": "Vilijampolė",
            "street": "Brastos g.",
            "rooms": 2,
            "area_m2": 45,
            "rent_eur": 600,
            "year_built": 2020,
            "reserved": False,
        }

        result = score_listing(listing)

        self.assertEqual(result["candidate_location_source"], "street_proxy")
        self.assertEqual(result["candidate_score_components"]["location"], 24.0)
        self.assertTrue(result["needs_coordinate_enrichment"])

    def test_generic_vilijampole_gets_weak_location_proxy(self):
        listing = {
            "listing_id": "4-4",
            "district": "Vilijampolė",
            "street": "Demokratų g.",
            "rooms": 2,
            "area_m2": 45,
            "rent_eur": 600,
            "year_built": 2020,
            "reserved": False,
        }

        result = score_listing(listing)

        self.assertEqual(result["candidate_score_components"]["location"], 10.0)
        self.assertEqual(result["candidate_location_source"], "district_proxy")

    def test_score_is_not_called_arbitrage_score(self):
        listing = {
            "listing_id": "4-5",
            "district": "Senamiestis",
            "street": "Vilniaus g.",
            "rooms": 1,
            "area_m2": 30,
            "rent_eur": 500,
            "year_built": 1900,
            "reserved": False,
        }

        result = score_listing(listing)

        self.assertIn("aruodas_candidate_score", result)
        self.assertNotIn("arbitrage_score", result)

    def test_ranking_puts_better_candidate_first(self):
        listings = [
            {
                "listing_id": "weak",
                "district": "Vilijampolė",
                "street": "Demokratų g.",
                "rooms": 1,
                "area_m2": 20,
                "rent_eur": 850,
                "year_built": 1970,
                "reserved": False,
            },
            {
                "listing_id": "strong",
                "district": "Senamiestis",
                "street": "Vilniaus g.",
                "rooms": 2,
                "area_m2": 45,
                "rent_eur": 550,
                "year_built": 2020,
                "reserved": False,
            },
        ]

        ranked = rank_listings(listings)

        self.assertEqual(ranked[0]["listing_id"], "strong")
        self.assertGreater(
            ranked[0]["aruodas_candidate_score"],
            ranked[1]["aruodas_candidate_score"],
        )


if __name__ == "__main__":
    unittest.main()
