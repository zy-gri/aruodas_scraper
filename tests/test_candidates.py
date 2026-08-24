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
        self.assertEqual(result["coordinate_enrichment_priority"], "SKIP")

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
        self.assertEqual(result["coordinate_enrichment_priority"], "DONE")
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
        self.assertEqual(result["candidate_location_confidence"], "low")
        self.assertEqual(result["candidate_score_components"]["location"], 24.0)
        self.assertTrue(result["needs_coordinate_enrichment"])
        self.assertEqual(result["coordinate_enrichment_priority"], "HIGH")

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

        self.assertEqual(result["candidate_score_components"]["location"], 7.0)
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
        self.assertEqual(result["candidate_scorer_version"], "aruodas-candidate-v2")

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

    def test_prime_street_beats_generic_centras(self):
        prime = {
            "listing_id": "prime",
            "district": "Centras",
            "street": "Laisvės al.",
            "rooms": 2,
            "area_m2": 40,
            "rent_eur": 600,
            "year_built": 2015,
            "reserved": False,
        }
        generic = {
            "listing_id": "generic",
            "district": "Centras",
            "street": "Tunelio g.",
            "rooms": 2,
            "area_m2": 40,
            "rent_eur": 600,
            "year_built": 2015,
            "reserved": False,
        }

        prime_result = score_listing(prime)
        generic_result = score_listing(generic)

        self.assertEqual(prime_result["candidate_score_components"]["location"], 35.0)
        self.assertEqual(generic_result["candidate_score_components"]["location"], 23.0)
        self.assertGreater(
            prime_result["aruodas_candidate_score"],
            generic_result["aruodas_candidate_score"],
        )

    def test_savanoriu_is_uncertain_not_prime_centras(self):
        listing = {
            "listing_id": "savanoriu",
            "district": "Centras",
            "street": "Savanorių pr.",
            "rooms": 1,
            "area_m2": 28,
            "rent_eur": 399,
            "year_built": 2020,
            "reserved": False,
        }

        result = score_listing(listing)

        self.assertEqual(result["candidate_location_source"], "street_proxy")
        self.assertEqual(result["candidate_location_confidence"], "low")
        self.assertEqual(result["candidate_score_components"]["location"], 18.0)
        self.assertNotEqual(result["candidate_tier"], "HIGH")

    def test_strong_unresolved_candidate_gets_high_enrichment_priority(self):
        listing = {
            "listing_id": "prime-enrich",
            "district": "Centras",
            "street": "Kęstučio g.",
            "rooms": 2,
            "area_m2": 40,
            "rent_eur": 650,
            "year_built": 2020,
            "reserved": False,
        }

        result = score_listing(listing)

        self.assertTrue(result["needs_coordinate_enrichment"])
        self.assertEqual(result["coordinate_enrichment_priority"], "HIGH")


if __name__ == "__main__":
    unittest.main()
