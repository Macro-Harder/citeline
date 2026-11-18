"""Repair test.

Oracle: the audit record finding the repair item,
disposed [defect] in the audit record
Part B: the guide Simple artefact lists the home failure
records twice, raw block then prose. The cure: they stand
once, in the prose form, with the reason the guide carries
them stated.
"""

import unittest

from citeline import reporting

AUDIT_DATE = "2026-11-17"


class TestP8O05GuideFailureRecordsOnce(unittest.TestCase):

    def _guide(self):
        return {
            "opening_text": "Example Product answers questions.",
            "actions": [],
            "score": {"value": 50},
            "failure_records": [{
                "operation": "audit",
                "error_value": "SUPPLIED_PATH_UNSAFE",
                "subject_identity": "page missing.md",
                "date": AUDIT_DATE,
                "rule_fired": "SUPPLIED_PATH_UNSAFE",
            }],
        }

    def test_failure_records_stand_once(self):
        text = reporting.render(self._guide(), "simple")
        self.assertEqual(text.count("SUPPLIED_PATH_UNSAFE"), 1)
        self.assertEqual(text.count("Failure records."), 1)
        self.assertNotIn("failure_records:", text)

    def test_guide_states_why_it_carries_them(self):
        text = reporting.render(self._guide(), "simple")
        section = text.split("Failure records.", 1)[1]
        self.assertIn("guide carries", section)


if __name__ == "__main__":
    unittest.main()
