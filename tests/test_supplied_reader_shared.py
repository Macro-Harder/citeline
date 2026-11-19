"""Every supplied file intake stands on the one shared
open protocol: the robots intake refuses a device in the
governed vocabulary at exit 5, and the page, answer, and
plan intakes read through the same implementation in
citeline.shared, so no intake keeps a private copy of the
protocol to drift."""

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
sys.exit(shell.main({argv!r}))
"""


class SharedSuppliedReaderTests(unittest.TestCase):
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

    def run_cli(self, argv):
        driver = DRIVER.format(root=str(PRODUCT_ROOT), argv=argv)
        return subprocess.run(
            [sys.executable, "-c", driver],
            capture_output=True, text=True, timeout=30,
            cwd=str(PRODUCT_ROOT))

    def assert_refused_unsafe(self, argv):
        result = self.run_cli(argv)
        self.assertEqual(result.returncode, 5)
        self.assertIn(
            "SUPPLIED_PATH_UNSAFE", result.stdout + result.stderr)

    def test_robots_of_dev_zero_refuses_unsafe(self):
        self.assert_refused_unsafe(
            ["robots", "--home", self.home, "--robots_file", "/dev/zero",
             "--form", "agentic"])


if __name__ == "__main__":
    unittest.main()
