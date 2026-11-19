"""The audit route judges a supplied page path through the
safe supplied file reader before any unbounded read: a
device file and a FIFO both refuse in the governed
vocabulary at exit 5, with no runaway read and no hang."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

DRIVER = """
import resource
import sys
resource.setrlimit(
    resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
sys.path.insert(0, {root!r})
from citeline import shell
sys.exit(shell.main(
    ["audit", "--home", {home!r}, "--page_file", {page!r},
     "--form", "agentic"]))
"""


class AuditSuppliedPathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = str(root / "home")
        sys.path.insert(0, str(PRODUCT_ROOT))
        from citeline import install as install_module
        from citeline import service
        install_module.install(
            location=str(root / "install"), home=self.home)
        service.add_product(
            home=self.home, name="Example Product",
            canonical_line=(
                "Example Product answers questions with citations."),
            domain="example.com", audit_date="2026-11-19")

    def run_audit_subprocess(self, page):
        driver = DRIVER.format(
            root=str(PRODUCT_ROOT), home=self.home, page=page)
        return subprocess.run(
            [sys.executable, "-c", driver],
            capture_output=True, text=True, timeout=30,
            cwd=str(PRODUCT_ROOT))

    def test_audit_of_dev_zero_refuses_unsafe_without_runaway_read(self):
        result = self.run_audit_subprocess("/dev/zero")
        self.assertEqual(result.returncode, 5)
        self.assertIn(
            "SUPPLIED_PATH_UNSAFE", result.stdout + result.stderr)

    def test_audit_of_fifo_refuses_unsafe_without_hanging(self):
        fifo = os.path.join(self.tmp.name, "page.fifo")
        os.mkfifo(fifo)
        result = self.run_audit_subprocess(fifo)
        self.assertEqual(result.returncode, 5)
        self.assertIn(
            "SUPPLIED_PATH_UNSAFE", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
