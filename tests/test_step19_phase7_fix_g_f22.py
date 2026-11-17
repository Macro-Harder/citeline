"""Step 19 Phase 7 fix seat G, item P7A3-F2-2 pinning tests.

The F-2 exception is a row field exception. Governing
text: the Phase 6 class (f) F-2 cure, the exception
binds the per answer rows of an answer_metrics list,
and a row's own control_flag states only that the
answer is a control answer. A control_flag nested
inside a row object is not a row's own field, and a
bare object under the key is no list of rows, so
neither stands excepted: each states a failed control
as a control_flag at any other depth does.
"""

import unittest

from citeline import reporting


def notice_forms(record):
    advanced = reporting.render(record, form="advanced")
    agentic = reporting.render(record, form="agentic")
    agentic_body = agentic["report"] if isinstance(
        agentic, dict) and "report" in agentic else agentic
    simple = reporting.render(record, form="simple")
    return advanced, agentic_body, simple


class TestControlNoticeShapeP7A3F22(unittest.TestCase):

    def test_direct_row_flag_still_excepted(self):
        record = {"answer_metrics": [{"control_flag": True}],
                  "control_failed": False}
        advanced, agentic_body, simple = notice_forms(record)
        self.assertNotIn("control_failure_notice", advanced)
        self.assertNotIn("control_failure_notice", agentic_body)
        self.assertNotIn("control failure", simple.lower())

    def test_flag_nested_inside_a_row_gains_notice(self):
        record = {"answer_metrics": [
                      {"detail": {"control_flag": True}}],
                  "control_failed": False}
        advanced, agentic_body, simple = notice_forms(record)
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertEqual(
            agentic_body.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertIn("control failure", simple.lower())

    def test_bare_object_under_the_key_gains_notice(self):
        record = {"answer_metrics": {"control_flag": True},
                  "control_failed": False}
        advanced, agentic_body, simple = notice_forms(record)
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertEqual(
            agentic_body.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertIn("control failure", simple.lower())

    def test_row_control_failed_still_gains_notice(self):
        record = {"answer_metrics": [{"control_failed": True}],
                  "control_failed": False}
        advanced, agentic_body, simple = notice_forms(record)
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertEqual(
            agentic_body.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)


if __name__ == "__main__":
    unittest.main()
