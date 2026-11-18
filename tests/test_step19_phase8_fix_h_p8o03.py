"""Repair test.

Oracle: the audit record finding the repair item,
disposed [defect] in the audit record
Part B: the Simple robots summary leaves 2 of 25 crawlers
unaccounted (23 reach, 0 barred; the 2 are control rows).
The cure: the Simple summary accounts for every crawler row
it covers, controls named as controls.
"""

import re
import unittest

from citeline import reporting


def robots_body():
    findings = []
    for index in range(23):
        findings.append({
            "token": "Crawler-%02d" % index,
            "outcome": "allowed",
            "purpose_class": "search",
            "evidence_label": "directly verified",
            "purpose_prose_evidence_label": "directly verified",
        })
    for token in ("Google-Extended", "Applebot-Extended"):
        findings.append({
            "token": token,
            "outcome": None,
            "purpose_class": "control",
            "evidence_label": "directly verified",
            "purpose_prose_evidence_label": "directly verified",
        })
    return {
        "evaluated_page_path": "/",
        "path_defaulted": True,
        "findings": findings,
    }


class TestP8O03RobotsSummaryAccountsForControls(unittest.TestCase):

    def test_summary_names_the_control_rows_as_controls(self):
        text = reporting.render(robots_body(), "simple")
        summary = text.splitlines()[1]
        self.assertIn("lets 23 of the 25 listed crawlers", summary)
        self.assertIn("bars 0", summary)
        self.assertIn("control rows", summary)
        self.assertIn("2", summary.split("control rows")[0])

    def test_summary_figures_sum_to_the_listed_total(self):
        text = reporting.render(robots_body(), "simple")
        summary = text.splitlines()[1]
        reached = int(re.search(r"lets (\d+) of the (\d+)", summary).group(1))
        total = int(re.search(r"lets (\d+) of the (\d+)", summary).group(2))
        barred = int(re.search(r"bars (\d+)", summary).group(1))
        controls = int(re.search(
            r"(\d+) of the listed crawlers are control rows",
            summary).group(1))
        self.assertEqual(reached + barred + controls, total)


if __name__ == "__main__":
    unittest.main()
