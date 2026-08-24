import unittest

from bs4 import BeautifulSoup

from src.parser import parse_listing


class SearchParserTests(unittest.TestCase):
    def _card(self, middle_tokens: str):
        html = f"""
        <div class="list-row-v2 object-row srentflat advert">
          <a href="https://www.aruodas.lt/butu-nuoma-kaune-centre-laisves-al-test-4-1234567/">
            <img data-id="1234567" data-objid="4"
                 alt="Centras, Laisvės al., 2 kambario buto nuoma"
                 data-default="https://example.com/main.jpg" />
          </a>
          <span>2 k.</span>
          <span>64 m²</span>
          <span>5/5 aukšt.</span>
          <span>1955 m.</span>
          {middle_tokens}
          <span>698 €</span>
          <span>10,91 €/m²</span>
        </div>
        """
        return BeautifulSoup(html, "lxml").select_one(
            "div.list-row-v2.object-row.srentflat.advert"
        )

    def test_price_increase_is_never_heating(self):
        card = self._card(
            "<span>Centrinis</span><span>Kaina padidėjusi 16,3%</span>"
        )
        result = parse_listing(card)

        self.assertEqual(result["heating"], "Centrinis")
        self.assertNotEqual(result["heating"], "Kaina padidėjusi 16,3%")

    def test_price_reduction_is_never_heating(self):
        card = self._card(
            "<span>Dujinis</span><span>Kaina sumažėjusi 7,1%</span>"
        )
        result = parse_listing(card)

        self.assertEqual(result["heating"], "Dujinis")
        self.assertEqual(result["price_reduction_pct"], 7.1)

    def test_combined_heating_is_preserved(self):
        card = self._card("<span>Centrinis, Dujinis</span>")
        result = parse_listing(card)

        self.assertEqual(result["heating"], "Centrinis, Dujinis")


if __name__ == "__main__":
    unittest.main()
