import unittest

from src.location import classify_location, extract_aruodas_coordinates


class LocationClassifierTests(unittest.TestCase):
    def test_extracts_aruodas_streetview_coordinate(self):
        html = (
            '<a class="show-streetview" '
            'href="https://www.google.com/maps/@?api=1&amp;map_action=pano&amp;'
            'viewpoint=54.903446,23.878100&amp;pitch=10&amp;fov=100">'
        )

        self.assertEqual(
            extract_aruodas_coordinates(html),
            (54.903446, 23.878100),
        )

    def test_known_brastos_listing_is_piliamiestis(self):
        result = classify_location(54.903446, 23.878100)

        self.assertEqual(result["location_zone"], "PILIAMIESTIS")
        self.assertEqual(result["location_grade"], "A")
        self.assertEqual(result["location_gate"], "keep")

    def test_rotuse_is_old_town_core(self):
        result = classify_location(54.896950, 23.885620)

        self.assertEqual(result["location_zone"], "OLD_TOWN_CORE")
        self.assertEqual(result["location_grade"], "A+")

    def test_laisves_aleja_is_laisves_core(self):
        result = classify_location(54.897328, 23.918977)

        self.assertEqual(result["location_zone"], "LAISVES_CORE")
        self.assertEqual(result["location_grade"], "A+")

    def test_arena_is_arena_zone(self):
        result = classify_location(54.889974, 23.914408)

        self.assertEqual(result["location_zone"], "ARENA_AKROPOLIS")
        self.assertEqual(result["location_grade"], "A")

    def test_basilica_is_central_zaliakalnis(self):
        result = classify_location(54.902000, 23.917000)

        self.assertEqual(result["location_zone"], "CENTRAL_ZALIAKALNIS")
        self.assertEqual(result["location_grade"], "B+")

    def test_far_point_requires_exceptional_economics(self):
        result = classify_location(54.920000, 23.960000)

        self.assertEqual(result["location_zone"], "OTHER_KAUNAS")
        self.assertEqual(
            result["location_gate"],
            "exceptional_economics_only",
        )


if __name__ == "__main__":
    unittest.main()
