"""Repair pinning tests.

The caller named kind form of round_metrics_from_journal.
Governing text: plan Section 5.1 RoundMetrics entry,
computed per source kind and never pooled across kinds,
and the round_metrics docstring, only answers of the
requested kind enter any figure. A record that names a
kind and counts that kind only must not attach per
answer rows of every kind beside those figures.
"""

import unittest

from citeline import metrics


REG = {"sequence": 1, "entry_kind": "product_registered",
       "payload": {"name": "Acme", "domain": "acme.example",
                   "aliases": ["Acme"], "competitors": [],
                   "query_set": ["q1"]}}
NAMED_CITED = ("Acme is great. See https://acme.example/page "
               "for details and more words here.")
PLAIN = "Some unrelated text about weather and cooking today."


def ans(seq, text, engine, method, date, kind="sampled", **extra):
    payload = {"answer_text": text, "query": "q1",
               "engine_label": engine, "capture_method": method,
               "captured_on": date, "kind": kind}
    payload.update(extra)
    return {"sequence": seq, "entry_kind": "answer_imported",
            "payload": payload}


class TestNamedKindRowsP7A3F13(unittest.TestCase):

    def test_named_kind_record_carries_only_named_kind_rows(self):
        entries = [
            REG,
            ans(2, NAMED_CITED, "engine-a", "manual copy",
                "2026-11-10", kind="sampled"),
            ans(3, NAMED_CITED, "engine-b", "export file",
                "2026-11-11", kind="real_sample"),
        ]
        record = metrics.round_metrics_from_journal(
            entries, kind="sampled")
        rows = record.get("answer_metrics") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [row.get("source_kind") for row in rows], ["sampled"])
        self.assertEqual(
            [row.get("engine_label") for row in rows], ["engine-a"])
        context = record.get("capture_context") or {}
        self.assertEqual(context.get("distinct_engines"), 1)
        self.assertEqual(context.get("engine_labels"), ["engine-a"])

    def test_named_kind_record_rows_recompute_its_figures(self):
        entries = [
            REG,
            ans(2, NAMED_CITED, "engine-a", "manual copy",
                "2026-11-10", kind="sampled"),
            ans(3, PLAIN, "engine-b", "export file",
                "2026-11-11", kind="real_sample"),
            ans(4, PLAIN, "engine-b", "export file",
                "2026-11-12", kind="real_sample"),
        ]
        record = metrics.round_metrics_from_journal(
            entries, kind="real_sample")
        rows = record.get("answer_metrics") or []
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(
            row.get("source_kind") == "real_sample" for row in rows))
        self.assertEqual(record.get("imported_count"), 2)


if __name__ == "__main__":
    unittest.main()
