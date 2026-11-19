"""An error inside detect_answer surfaces to the caller of
the metrics recomputation: no second, cruder detector takes
over silently and no figures are produced from it."""

import unittest
from unittest import mock

from citeline import detection, metrics


def journal_entries():
    return [
        {
            "sequence": 1,
            "entry_kind": "product_registered",
            "payload": {
                "name": "Example Product",
                "product_id": "p-0",
                "canonical_line": (
                    "Example Product answers questions "
                    "with citations."),
                "domain": "example.com",
                "aliases": [],
                "competitors": [],
            },
        },
        {
            "sequence": 2,
            "entry_kind": "answer_imported",
            "payload": {
                "answer_text": (
                    "Example Product is a fine choice for "
                    "the job."),
                "query": "best tool",
                "engine_label": "engine-a",
            },
        },
    ]


class DetectAnswerErrorSurfacingTests(unittest.TestCase):
    def test_detect_answer_error_propagates_out_of_recomputation(self):
        with mock.patch.object(
                detection, "detect_answer",
                side_effect=RuntimeError("detector broke")):
            with self.assertRaises(RuntimeError):
                metrics.answer_metrics_from_journal(
                    journal_entries())

    def test_detect_answer_result_is_used_when_it_runs(self):
        rows = metrics.answer_metrics_from_journal(
            journal_entries())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["named"])


if __name__ == "__main__":
    unittest.main()
