import tempfile
import unittest
from pathlib import Path

from src.detail_merge import listing_id_from_detail_filename, merge_detail_locations


DETAIL_HTML = """
<div>Taškas žemėlapyje netikslus</div>
<a class="show-streetview street-view-button"
   href="https://www.google.com/maps/@?api=1&amp;map_action=pano&amp;viewpoint=54.903446,23.878100&amp;pitch=10">
  Gatvės v.
</a>
"""


class DetailMergeTests(unittest.TestCase):
    def test_listing_id_is_read_from_detail_filename(self):
        self.assertEqual(
            listing_id_from_detail_filename("detail_4-1479506.html"),
            "4-1479506",
        )
        self.assertIsNone(listing_id_from_detail_filename("page_01.html"))

    def test_matching_detail_is_merged_without_overwriting_baseline(self):
        baseline = [
            {
                "listing_id": "4-1479506",
                "rent_eur": 898.0,
                "rooms": 3,
                "district": "Vilijampolė",
            },
            {
                "listing_id": "4-9999999",
                "rent_eur": 500.0,
                "rooms": 2,
                "district": "Centras",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            detail_path = Path(temp_dir) / "detail_4-1479506.html"
            detail_path.write_text(DETAIL_HTML, encoding="utf-8")

            enriched, report = merge_detail_locations(baseline, [detail_path])

        matched = next(row for row in enriched if row["listing_id"] == "4-1479506")
        missing = next(row for row in enriched if row["listing_id"] == "4-9999999")

        self.assertEqual(matched["rent_eur"], 898.0)
        self.assertEqual(matched["rooms"], 3)
        self.assertEqual(matched["location_zone"], "PILIAMIESTIS")
        self.assertEqual(matched["location_grade"], "A")
        self.assertEqual(matched["location_score"], 92)
        self.assertTrue(matched["coordinates_found"])
        self.assertTrue(matched["aruodas_map_approximate"])
        self.assertEqual(matched["location_enrichment_status"], "enriched")

        self.assertEqual(missing["location_enrichment_status"], "detail_missing")
        self.assertIsNone(missing["latitude"])

        self.assertEqual(report["baseline_listings"], 2)
        self.assertEqual(report["matched_detail_files"], 1)
        self.assertEqual(report["coordinates_found"], 1)
        self.assertEqual(report["baseline_without_detail"], 1)

    def test_unmatched_detail_file_is_reported(self):
        baseline = [{"listing_id": "4-1111111", "rent_eur": 500.0}]

        with tempfile.TemporaryDirectory() as temp_dir:
            detail_path = Path(temp_dir) / "detail_4-2222222.html"
            detail_path.write_text(DETAIL_HTML, encoding="utf-8")

            _, report = merge_detail_locations(baseline, [detail_path])

        self.assertEqual(
            report["unmatched_detail_files"],
            ["detail_4-2222222.html"],
        )


if __name__ == "__main__":
    unittest.main()
