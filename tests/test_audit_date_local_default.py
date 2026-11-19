"""A dateless audit defaults audit_date to the local
calendar date, not the UTC date, and the agentic render
carries audit_date_defaulted when the date defaulted. The
test picks a zone whose local date always differs from
the UTC date at the hour it runs, so the two readings can
never agree by accident."""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

DRIVER = """
import json
import sys
sys.path.insert(0, {root!r})
from citeline import install as install_module
from citeline import reporting, service
home = {home!r}
install_module.install(location={location!r}, home=home)
service.add_product(
    home=home, name="Example Product",
    canonical_line="Example Product is a citability tool.",
    domain="example.com", audit_date="2026-11-18")
record = service.audit(home=home, page_file={page!r})
envelope = reporting.render(record, form="agentic")
print(json.dumps({{
    "audit_date": record["audit_date"],
    "defaulted": record["audit_date_defaulted"],
    "render_defaulted": envelope["report"].get(
        "audit_date_defaulted"),
}}))
"""


class LocalAuditDateDefaultTests(unittest.TestCase):
    def test_dateless_audit_stores_local_date_and_renders_flag(self):
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        if utc_now.hour >= 10:
            # A POSIX zone spec at UTC+14: the local date
            # stands one day ahead of the UTC date.
            zone = "KIR-14"
            offset = datetime.timedelta(hours=14)
        else:
            # A POSIX zone spec at UTC-10: the local date
            # stands one day behind the UTC date.
            zone = "HST10"
            offset = datetime.timedelta(hours=-10)
        expected_local = (utc_now + offset).date().isoformat()
        utc_today = utc_now.date().isoformat()
        self.assertNotEqual(expected_local, utc_today)
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            driver = DRIVER.format(
                root=str(PRODUCT_ROOT), home=home,
                location=os.path.join(tmp, "install"),
                page=str(PRODUCT_ROOT / "tests" / "fixtures"
                         / "w7-page.md"))
            env = dict(os.environ, TZ=zone)
            result = subprocess.run(
                [sys.executable, "-c", driver],
                capture_output=True, text=True, timeout=60,
                cwd=str(PRODUCT_ROOT), env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            outcome = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(outcome["audit_date"], expected_local)
        self.assertIs(outcome["defaulted"], True)
        self.assertIs(outcome["render_defaulted"], True)


if __name__ == "__main__":
    unittest.main()
