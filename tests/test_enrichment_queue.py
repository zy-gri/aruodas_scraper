import unittest

from src.enrichment_queue import build_enrichment_queue


class EnrichmentQueueTests(unittest.TestCase):
    def test_queue_skips_rejects_and_marks_existing_enrichment(self):
        candidates = [
            {
                "listing_id": "a",
                "candidate_tier": "HIGH",
                "aruodas_candidate_score": 90,
                "rent_eur": 500,
            },
            {
                "listing_id": "b",
                "candidate_tier": "REJECT",
                "aruodas_candidate_score": 95,
                "rent_eur": 300,
            },
            {
                "listing_id": "c",
                "candidate_tier": "PROMISING",
                "aruodas_candidate_score": 82,
                "rent_eur": 600,
            },
        ]
        enrichments = [{"listing_id": "a", "listing_scope": "whole_apartment"}]

        queue = build_enrichment_queue(candidates, enrichments, limit=30)

        self.assertEqual([item["listing_id"] for item in queue], ["a", "c"])
        self.assertEqual(queue[0]["rank"], 1)
        self.assertEqual(queue[0]["text_enrichment_status"], "already_enriched")
        self.assertEqual(queue[1]["text_enrichment_status"], "needed")

    def test_queue_respects_limit(self):
        candidates = [
            {
                "listing_id": str(i),
                "candidate_tier": "HIGH",
                "aruodas_candidate_score": 100 - i,
            }
            for i in range(10)
        ]

        queue = build_enrichment_queue(candidates, [], limit=3)

        self.assertEqual(len(queue), 3)
        self.assertEqual([item["listing_id"] for item in queue], ["0", "1", "2"])


if __name__ == "__main__":
    unittest.main()
