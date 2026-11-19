"""Journal verify cache tamper resistance.

A verify served from the scan cache must stand on the journal
bytes as they stand, never on file metadata alone: a same size
tamper whose stat key collides with the key of the cached scan
(coarse timestamp granularity, a restored modification time)
must still fail verification.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal


class VerifyCacheTamperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def append_product(self, name, product_id):
        return journal.append_entry(
            self.home, "product_registered",
            {"name": name, "product_id": product_id})

    def test_same_size_tamper_fails_verify_when_stat_key_collides(self):
        self.append_product("Product 0", "p-0")
        self.append_product("Product 1", "p-1")
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        path = journal.journal_path(self.home)
        before = os.stat(path)
        frozen = journal._stat_key(path)
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        index = data.index(b"Product 0")
        data[index + 8] = ord("X")
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        # A filesystem whose timestamp granularity lets a tamper
        # reproduce the cached scan's stat key exactly: the key
        # stands frozen at its pre-tamper value for this call.
        with mock.patch.object(journal, "_stat_key",
                               return_value=frozen):
            result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["token"], "JOURNAL_VERIFY_FAILED")

    def test_same_size_tamper_fails_verify_in_one_process(self):
        # The filed issue's repro sequence: verify, tamper one
        # byte in the last entry leaving size unchanged, verify
        # again in the same process.
        self.append_product("Product 0", "p-0")
        self.append_product("Product 1", "p-1")
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        path = journal.journal_path(self.home)
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        data[-2] ^= 1
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        self.assertFalse(journal.verify_chain(self.home)["passed"])


if __name__ == "__main__":
    unittest.main()
