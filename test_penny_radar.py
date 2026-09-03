import json
import tempfile
import unittest
from pathlib import Path

from collect_home_depot_penny import classify, run
from collect_scrapedo_home_depot import _product_from_html


class PennyRadarTests(unittest.TestCase):
    def test_deep_clearance(self):
        status, score, _ = classify({"price": 20, "regularPrice": 100})
        self.assertEqual(status, "HIGH PROBABILITY")
        self.assertEqual(score, 65)

    def test_unconfirmed_penny(self):
        status, score, _ = classify({"price": 0.01, "regularPrice": 10})
        self.assertEqual(status, "PENNY CANDIDATE")
        self.assertEqual(score, 90)

    def test_confirmed_requires_physical_method(self):
        status, score, _ = classify({"price": 0.01, "regularPrice": 10, "confirmationMethod": "store_scan"})
        self.assertEqual((status, score), ("CONFIRMED", 100))

    def test_parses_product_json_ld(self):
        html = '''<script type="application/ld+json">{"@type":"Product","name":"Test Tool","sku":"1001","brand":{"name":"RIDGID"},"offers":{"price":19.97,"availability":"https://schema.org/InStock"}}</script>'''
        item = _product_from_html(html, "https://www.homedepot.com/p/x/123", "zip:33189")
        self.assertEqual(item["sku"], "1001")
        self.assertEqual(item["price"], 19.97)

    def test_incomplete_capture_never_marks_disappearance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obs = root / "obs.json"
            history = root / "history.json"
            output = root / "out.json"
            obs.write_text(json.dumps({"captureComplete": False, "capturedStoreIds": ["zip:33189"], "items": []}))
            history.write_text(json.dumps({"products": {"zip:33189|1": {"latest": {"price": 20, "regularPrice": 100}}}}))
            result = run(obs, history, output)
            self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
