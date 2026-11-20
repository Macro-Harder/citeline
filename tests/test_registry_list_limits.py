"""Repair tests: registry list limits in force.

Oracle: the settled rule. The registry list limits read
the config in force for the home, not hardcoded values: a
lowered limit refuses a set above it, and a raised limit
admits a set past the brief default.
"""

import os
import tempfile
import unittest

from citeline import registry, service

AUDIT_DATE = "2026-11-17"
PRODUCT = "Example Product"


def token_of(exc):
    return getattr(exc, "error_value", None) or getattr(
        exc, "token", None) or str(exc)


class RegistryLimitsBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, lines):
        with open(os.path.join(self.home, "config.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def add_default(self):
        return service.add_product(
            home=self.home, name=PRODUCT,
            canonical_line="The reference sentence.",
            domain="example.invalid", audit_date=AUDIT_DATE)


class TestLoweredLimitsInForce(RegistryLimitsBase):

    def setUp(self):
        super().setUp()
        self.write_config([
            "competitors_per_product = 10",
            "aliases_per_product = 5",
            "queries_per_product = 3",
        ])
        self.add_default()

    def test_competitors_above_limit_in_force_refused(self):
        names = [{"name": "Rival %02d" % i} for i in range(11)]
        with self.assertRaises(Exception) as caught:
            service.set_competitors(
                home=self.home, product=PRODUCT, competitors=names,
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        record = registry.get_product(self.home, PRODUCT)
        self.assertEqual(record["competitors"], [])

    def test_aliases_above_limit_in_force_refused(self):
        with self.assertRaises(Exception) as caught:
            service.set_aliases(
                home=self.home, product=PRODUCT,
                aliases=["alias%d" % i for i in range(6)],
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_queries_above_limit_in_force_refused(self):
        with self.assertRaises(Exception) as caught:
            service.set_query_set(
                home=self.home, product=PRODUCT,
                query_set=["q%d" % i for i in range(4)],
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_sets_at_the_limit_in_force_admitted(self):
        service.set_competitors(
            home=self.home, product=PRODUCT,
            competitors=[{"name": "Rival %02d" % i} for i in range(10)],
            audit_date=AUDIT_DATE)
        service.set_aliases(
            home=self.home, product=PRODUCT,
            aliases=["alias%d" % i for i in range(5)], audit_date=AUDIT_DATE)
        service.set_query_set(
            home=self.home, product=PRODUCT,
            query_set=["q%d" % i for i in range(3)],
            audit_date=AUDIT_DATE)


class TestRaisedLimitInForce(RegistryLimitsBase):

    def test_raised_competitor_limit_admits_past_the_default(self):
        self.write_config(["competitors_per_product = 150"])
        self.add_default()
        names = [{"name": "Rival %03d" % i} for i in range(101)]
        updated = service.set_competitors(
            home=self.home, product=PRODUCT, competitors=names,
            audit_date=AUDIT_DATE)
        record = updated.get("product", updated) \
            if isinstance(updated, dict) else updated
        self.assertEqual(len(record["competitors"]), 101)


if __name__ == "__main__":
    unittest.main()
