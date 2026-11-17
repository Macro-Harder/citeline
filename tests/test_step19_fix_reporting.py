"""Step 19 repair tests, fix seat 7 (reporting, metrics, guide, README).

Each test pins one repair queue item's stated cure. The tests
stand written before the cures they pin.
"""
import os
import unittest

from citeline import reporting

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def readme_text():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
        return " ".join(handle.read().split())


class TestR19056CountOnlyRateLine(unittest.TestCase):
    """R19-056: the count only branch of the Simple probe report
    rate line carries the small sample warning the stored record
    holds, never states that no rate is given while showing an
    interval, and counts one answer in the singular."""

    def test_count_only_line_at_n1(self):
        node = {
            "rate": 1.0, "wilson_low": 0.21, "wilson_high": 1.0,
            "tier": "count only", "count": 1, "n": 1,
            "small_sample_warning": True,
        }
        line = reporting._rate_line("named", node)
        self.assertIn("Small sample warning", line)
        self.assertNotIn("no rate is given", line)
        self.assertIn("1 answer,", line)
        self.assertNotIn("1 answers", line)


class TestR19055SimpleOpensWithProseSummary(unittest.TestCase):
    """R19-055: a Simple artefact on the generic surfaces opens
    with a prose summary sentence, not with a raw field name."""

    def test_status_simple_opens_with_prose(self):
        body = {
            "head_hash": "abc123", "entry_count": 3,
            "home_size": 1200, "home_path": "/tmp/home",
            "chain_result": "chain verifies",
        }
        text = reporting.render(body, "simple")
        first = text.splitlines()[0]
        self.assertNotIn("head_hash", first)
        self.assertIn("journal", first)

    def test_verify_simple_opens_with_prose(self):
        body = {"passed": True, "entry_count": 2,
                "chain_result": "chain verifies"}
        text = reporting.render(body, "simple")
        first = text.splitlines()[0]
        self.assertNotIn("passed:", first)
        self.assertIn("verifies", first)


class TestR19054FirstRoundWorkflow(unittest.TestCase):
    """R19-054: the README states the first round workflow in
    work order, with values."""

    def test_workflow_stated_in_order(self):
        text = readme_text()
        audit_at = text.find("creates the snapshot")
        register_at = text.find("register-page takes that snapshot")
        round_at = text.find("must be named before")
        guide_at = text.find("guide identity")
        for position in (audit_at, register_at, round_at, guide_at):
            self.assertGreaterEqual(position, 0)
        self.assertLess(audit_at, register_at)
        self.assertLess(register_at, round_at)

    def test_snapshot_identifier_not_a_file(self):
        text = readme_text()
        self.assertIn("snapshot identifier and not a file", text)


class TestR19090WatchBound(unittest.TestCase):
    """R19-090: the README states the product schedules nothing,
    an external scheduler runs the watch command, one invocation
    is one round only, and cadence is an operator statement."""

    def test_bound_stated(self):
        text = readme_text()
        self.assertIn("schedules nothing", text)
        self.assertIn("external scheduler", text)
        self.assertIn("one invocation is one round only", text)
        self.assertIn("not a product promise", text)
        self.assertNotIn("Runs scheduled watch rounds", text)


if __name__ == "__main__":
    unittest.main()
