"""Step 19 fix tests for R19-008: a register-page repeat writes nothing.

Oracle: register item R19-008 and brief CL19-177. A repeat
register-page call on a snapshot already marked is_product_page
writes nothing, matching the add-product no change rule, and
returns the standing registered record.
"""

import hashlib
import os
import tempfile
import unittest

from citeline import acquisition, service

AUDIT_DATE = "2026-11-17"
PRODUCT = "Example Product"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def home_bytes(home):
    total = {}
    for root, _dirs, files in os.walk(home):
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as handle:
                total[os.path.relpath(path, home)] = hashlib.sha256(
                    handle.read()).hexdigest()
    return total


class TestRegisterPageRepeat(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_repeat_register_page_writes_nothing(self):
        product = service.add_product(
            home=self.home, name=PRODUCT,
            canonical_line="The reference sentence.",
            domain="example.invalid", audit_date=AUDIT_DATE)
        page = os.path.join(self.tmp.name, "page.txt")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("Body text stands here.\n")
        created = acquisition.extract_page(
            home=self.home, product_id=field(product, "product_id"),
            page_path=page, audit_date=AUDIT_DATE)
        snapshot_id = field(field(created, "snapshot"), "snapshot_id")
        first = service.register_page(
            home=self.home, product=PRODUCT, snapshot=snapshot_id,
            audit_date=AUDIT_DATE)
        self.assertTrue(field(first, "is_product_page"))
        before = home_bytes(self.home)
        second = service.register_page(
            home=self.home, product=PRODUCT, snapshot=snapshot_id,
            audit_date=AUDIT_DATE)
        self.assertTrue(field(second, "is_product_page"))
        self.assertEqual(field(second, "snapshot_id"), snapshot_id)
        self.assertEqual(home_bytes(self.home), before)


if __name__ == "__main__":
    unittest.main()
