"""Step 19 repair test for R19-075, the one named folding call.

Oracle: plan decisions D-KF-153-CALL and D-KF-153-VER
name one folding call, str.casefold, for the consumer
routes. The behavioural gap is masked downstream on
the host routes by idna nameprep and on the token
routes by ASCII bounded patterns, so the pin stands
at the named call form at the five sites the register
names, beside a folding behaviour guard on the public
host route.
"""

import inspect
import unittest

from citeline import checks, detection


class TestR19075CasefoldOnly(unittest.TestCase):
    def test_no_casefold_then_lower_remains(self):
        for module in (checks, detection):
            self.assertNotIn(
                "casefold().lower()", inspect.getsource(module))

    def test_lower_only_sites_now_fold(self):
        source = inspect.getsource(checks)
        self.assertNotIn('split(":", 1)[0].lower()', source)
        self.assertIn('split(":", 1)[0].casefold()', source)
        self.assertNotIn("text[cursor:word_end].lower()", source)
        self.assertIn("text[cursor:word_end].casefold()", source)
        self.assertNotIn("sentence.lower()", source)
        self.assertIn("sentence.casefold()", source)

    def test_host_route_still_folds(self):
        self.assertEqual(
            detection.normalise_host("WWW.Example.COM."),
            "www.example.com")


if __name__ == "__main__":
    unittest.main()
