"""Step 19 Phase 7 fix seat G, item P7A3-F2-1 pinning test.

The fused key limb: answermetrics. Governing text: the
reporting module component reading, a fused name stands
on the same components as its separated form, the
reading the flag names and the notice keys in the
control failure notice pass already stand under. The
fused form of answer_metrics therefore names the per
answer rows container as the separated form does, and
a passing control row under it gains no notice.
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


class TestControlNoticeFusedKeyP7A3F21(unittest.TestCase):

    def test_fused_key_passing_control_carries_no_notice(self):
        record = {"answermetrics": [{"control_flag": True}],
                  "control_failed": False}
        advanced, agentic_body, simple = notice_forms(record)
        self.assertNotIn("control_failure_notice", advanced)
        self.assertNotIn("control_failure_notice", agentic_body)
        self.assertNotIn("control failure", simple.lower())


if __name__ == "__main__":
    unittest.main()
