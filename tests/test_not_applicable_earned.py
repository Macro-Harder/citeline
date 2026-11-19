"""A check whose status stands not_applicable carries no
earned fraction: the comparison check on a product with
no category terms stands with earned None and status
not_applicable, as description_consistency already did,
and no not_applicable record in a run carries a number
the status disowns."""

import unittest

from citeline import checks


def _page():
    return {
        "running_text": (
            "Example Product is a citability tool. "
            "It checks pages."),
        "sentences": [
            "Example Product is a citability tool.",
            "It checks pages."],
        "format": "markdown",
    }


def _facts(**overrides):
    facts = {
        "product_name": "Example Product",
        "canonical_line": "Example Product is a citability tool.",
        "aliases": ["Example Product"],
        "domain": "example.com",
        "is_product_page": True,
        "competitors": ["Rival One"],
        "category_terms": ["citability"],
    }
    facts.update(overrides)
    return facts


class NotApplicableEarnedTests(unittest.TestCase):
    def run_named(self, facts):
        results = checks.run_checks(_page(), facts)
        return {r["check_id"]: r for r in results}

    def test_comparison_without_category_terms_earns_none(self):
        named = self.run_named(_facts(category_terms=[]))
        comparison = named["comparison"]
        self.assertEqual(comparison["status"], "not_applicable")
        self.assertIsNone(comparison["earned"])
        self.assertEqual(comparison["reason_code"], "CMP_NA")

    def test_comparison_applicable_keeps_its_earned(self):
        named = self.run_named(_facts())
        comparison = named["comparison"]
        self.assertIsNotNone(comparison["earned"])

    def test_no_not_applicable_record_carries_earned(self):
        named = self.run_named(_facts(category_terms=[]))
        for record in named.values():
            if record["status"] == "not_applicable":
                self.assertIsNone(record["earned"], record["check_id"])


if __name__ == "__main__":
    unittest.main()
