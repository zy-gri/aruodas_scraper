import unittest

from src.detail_parser import parse_detail_html


class DetailParserTests(unittest.TestCase):
    def test_brastos_detail_location_is_piliamiestis(self):
        html = """
        <div class="show-map-line-inner">
          <div class="map__label">
            <div class="label">Žiūrėti žemėlapį</div>
            <div class="sublabel">Taškas <span class="red">netikslus</span></div>
          </div>
        </div>
        <a class="show-streetview street-view-button"
           href="https://www.google.com/maps/@?api=1&amp;map_action=pano&amp;viewpoint=54.903446,23.878100&amp;pitch=10&amp;fov=100">
          Gatvės v.
        </a>
        """

        result = parse_detail_html(html)

        self.assertTrue(result["coordinates_found"])
        self.assertTrue(result["aruodas_map_approximate"])
        self.assertEqual(result["latitude"], 54.903446)
        self.assertEqual(result["longitude"], 23.8781)
        self.assertEqual(result["map_accuracy"], "approximate")
        self.assertEqual(result["location_zone"], "PILIAMIESTIS")
        self.assertEqual(result["location_grade"], "A")
        self.assertEqual(result["location_gate"], "keep")

    def test_missing_coordinates_is_handled_cleanly(self):
        html = "<html><body><h1>Apartment</h1></body></html>"

        result = parse_detail_html(html)

        self.assertFalse(result["coordinates_found"])
        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])
        self.assertIsNone(result["location_zone"])

    def test_coordinate_without_inaccurate_label_has_unknown_accuracy(self):
        html = (
            '<a class="show-streetview" '
            'href="https://www.google.com/maps/@?api=1&amp;map_action=pano&amp;'
            'viewpoint=54.896950,23.885620&amp;pitch=10">Street View</a>'
        )

        result = parse_detail_html(html)

        self.assertTrue(result["coordinates_found"])
        self.assertFalse(result["aruodas_map_approximate"])
        self.assertEqual(result["map_accuracy"], "unknown")
        self.assertEqual(result["location_zone"], "OLD_TOWN_CORE")


if __name__ == "__main__":
    unittest.main()
