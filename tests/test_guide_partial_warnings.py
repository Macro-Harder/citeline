"""A guide draft names work for partial earnings: a check
that earned in part fires its WARN_ trigger and lists its
action, a check that earned nothing fires FAIL_, and a
check that earned in full or stands not applicable fires
nothing."""

import unittest

from citeline import guide

CANONICAL = "Example Product answers questions with citations."


def _record(checks):
    return {
        "run_id": "run-1",
        "product_id": "p-example-product",
        "canonical_line": CANONICAL,
        "product_name": "Example Product",
        "audit_date": "2026-11-18",
        "checks": checks,
        "score": {"value": 65.0},
    }


def _check(check_id, earned, status=None, weight=8):
    return {"check_id": check_id, "earned": earned,
            "status": status, "weight": weight}


def _codes(draft):
    return [a["code"] for a in draft["actions"]]


class GuidePartialWarningTests(unittest.TestCase):
    def draft(self, checks):
        return guide.draft_from_audit_record(
            _record(checks),
            sentences=[
                "Example Product recorded 42 percent growth in "
                "the 2025 review."],
            distinct_cited_target_count=2)

    def test_partial_earning_lists_a_warning_action(self):
        draft = self.draft([_check("keyword_stuffing", 0.25)])
        self.assertIn("WARN_KEYWORD", _codes(draft))

    def test_zero_earning_lists_a_failure_action(self):
        draft = self.draft([_check("keyword_stuffing", 0)])
        self.assertIn("FAIL_KEYWORD", _codes(draft))
        self.assertNotIn("WARN_KEYWORD", _codes(draft))

    def test_full_and_not_applicable_earn_no_action(self):
        draft = self.draft([
            _check("keyword_stuffing", 1.0),
            _check("comparison", None, status="not_applicable"),
        ])
        self.assertEqual(_codes(draft), [])


if __name__ == "__main__":
    unittest.main()
