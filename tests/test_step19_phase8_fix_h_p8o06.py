"""Step 19 Phase 8 fix test, seat H, item P8O-06.

Oracle: design/audit/step-19-phase8-orange.md finding P8O-06,
disposed [defect] in design/audit/step-19-phase8-triage.md
Part B: the audit error prefix "supplied path cannot be
stated" survives ahead of its own plain clause. The cure:
the message stands with the plain clause alone, in first
position.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import errors
from citeline import install as install_module
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
        self.assertNotEqual(code, 0)
        text = err.getvalue()
        self.assertNotIn("cannot be stated", text)
        self.assertIn("SUPPLIED_PATH_UNSAFE: the file does not exist",
                      text)
        self.assertIn("Next step", text)
        self.assertIn("Nothing was stored", text)


if __name__ == "__main__":
    unittest.main()
