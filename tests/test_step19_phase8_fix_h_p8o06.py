"""Step 19 Phase 8 fix test, seat H, item P8O-06.

Oracle: design/audit/step-19-phase8-orange.md finding P8O-06,
disposed [defect] in design/audit/step-19-phase8-triage.md
Part B: the audit error prefix "supplied path cannot be
stated" survives ahead of its own plain clause. The cure:
the message stands with the plain clause alone, in first
position.

Restatement, Step 20 seat FX20-09: the missing page pin in
this file stated the superseded behaviour for a supplied
path that does not exist. Delegated decision 5 of the
Step 20 register (R19-087) decides that a supplied path
that does not exist is an operator input fault and takes
the input class, not exit 5, and the FX20-07 cure lands
that decision: a missing page file takes
PAGE_EXTRACTION_FAILED, row X-14, at exit 2 at the
acquisition intake, and a missing robots file takes
VALIDATION_FAILED at the robots intake, while a supplied
path that exists but is not a regular file, a directory
for example, still takes SUPPLIED_PATH_UNSAFE at exit 5
under row X-4. The missing page pin stands restated to
that behaviour in its original strength, and the robots
and directory limbs of the same decision stand pinned
beside it. The recorded error pin above it stands as it
stood: it constructs its own error value and pins the
prefix rule, which the decision does not reach.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import errors
from citeline import install as install_module
from citeline import robots
from citeline import service
from citeline import shell

AUDIT_DATE = "2026-11-17"


class TestP8O06SuppliedPathPlainClauseAlone(unittest.TestCase):

    def test_recorded_error_drops_the_internal_prefix(self):
        err = errors.CitelineError(
            "supplied path cannot be stated: "
            "[Errno 2] No such file or directory: '/x/page.md'",
            token="SUPPLIED_PATH_UNSAFE")
        record = service.recorded_error(err)
        self.assertNotIn("cannot be stated", record["message"])
        self.assertTrue(
            record["message"].startswith("[Errno 2]"))

    def test_shell_audit_missing_page_message(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location = root / "install"
        home = root / "home"
        install_module.install(location=str(location), home=str(home))
        missing = root / "no-such-page.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = shell.main(
                ["audit", "--home", str(home),
                 "--page_file", str(missing),
                 "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertEqual(code, 2)
        text = err.getvalue()
        self.assertNotIn("cannot be stated", text)
        self.assertNotIn("SUPPLIED_PATH_UNSAFE", text)
        self.assertIn(
            "PAGE_EXTRACTION_FAILED: the supplied page file "
            "does not exist", text)
        self.assertIn("Next step", text)
        self.assertIn("Nothing was stored", text)

    def test_missing_robots_file_takes_input_class(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        missing = root / "no-such-robots.txt"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_file(str(missing))
        self.assertEqual(caught.exception.token, "VALIDATION_FAILED")
        self.assertNotEqual(
            caught.exception.token, "SUPPLIED_PATH_UNSAFE")
        self.assertIn("does not exist", str(caught.exception))

    def test_existing_directory_page_file_stays_integrity(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location = root / "install"
        home = root / "home"
        install_module.install(location=str(location), home=str(home))
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(home), page_file=str(root),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            caught.exception.token, "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.exit_code, 5)


if __name__ == "__main__":
    unittest.main()
