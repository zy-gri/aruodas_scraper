import json
import tempfile
import unittest
from pathlib import Path

from src.enrichment_io import load_enrichments


class EnrichmentIoTests(unittest.TestCase):
    def test_load_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "one.json"
            path.write_text(
                json.dumps([{"listing_id": "4-1", "listing_scope": "whole_apartment"}]),
                encoding="utf-8",
            )

            result = load_enrichments(path)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["listing_id"], "4-1")

    def test_directory_merges_batches_and_later_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aruodas_text_enrichment_a.json").write_text(
                json.dumps([
                    {"listing_id": "4-1", "description_summary": "old"},
                    {"listing_id": "4-2", "description_summary": "second"},
                ]),
                encoding="utf-8",
            )
            (root / "aruodas_text_enrichment_b.json").write_text(
                json.dumps([
                    {"listing_id": "4-1", "description_summary": "new"}
                ]),
                encoding="utf-8",
            )

            result = load_enrichments(root)
            by_id = {item["listing_id"]: item for item in result}

            self.assertEqual(len(result), 2)
            self.assertEqual(by_id["4-1"]["description_summary"], "new")
            self.assertEqual(by_id["4-2"]["description_summary"], "second")


if __name__ == "__main__":
    unittest.main()
