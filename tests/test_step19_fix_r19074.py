"""Step 19 fix tests for R19-074: the exit code fallback.

Oracle: register item R19-074 and plan EC-126 subsection 4.2. A
subcommand returns the code of the class of the one error value
it reports. An exception carrying no reported error value never
receives the domain code 3; it receives code 1, the code the
EC-126 table reserves in practice for a death carrying no
error value.
"""

import unittest

from citeline import errors, shell


class TestExitCodeFallback(unittest.TestCase):

    def test_unclassified_exception_gets_no_domain_code(self):
        code = shell._exit_code_for(Exception("boom"))
        self.assertEqual(code, 1)
        self.assertNotEqual(code, 3)

    def test_unknown_token_gets_no_domain_code(self):
        class Tokened(Exception):
            token = "NO_SUCH_VALUE"
        self.assertEqual(shell._exit_code_for(Tokened("boom")), 1)

    def test_known_token_keeps_its_class_code(self):
        exc = errors.CitelineError("boom", token="VALIDATION_FAILED")
        self.assertEqual(shell._exit_code_for(exc), 2)

    def test_stated_exit_code_stands(self):
        class Stated(Exception):
            exit_code = 5
        self.assertEqual(shell._exit_code_for(Stated("boom")), 5)


if __name__ == "__main__":
    unittest.main()
