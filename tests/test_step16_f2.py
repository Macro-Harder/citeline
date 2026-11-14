"""Step 16 fix wave, builder F2: metrics and service assembly.

Tests for defects D-02, D-05, and D-23 of the Step 16 round 1
fix register, written before the cures.

D-02: the importer declaration recorded at round naming, in
the journal round_named entry, must reach the sampling frame
of the probe report and of each trend round report, through
both limbs that carry it: the metrics journal route and the
service assembly datum.

D-05: guard G3 dominance. Where any one asserted engine
label, query, or day supplies more than half of a round, the
composition carries a dominance note. No axis is exempt for
holding one value only, so a round supplied wholly by one
engine at 100.0 percent reports dominance.

D-23: the Advanced probe trend carries the honesty sentence
at trend level and inside both embedded round reports, as
the standalone probe report does, including where the trend
itself stands on a series break.
"""

import os
import tempfile
import unittest
from pathlib import Path

from citeline import metrics, service
from citeline.reporting import HONESTY_SENTENCE

FIXTURES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures")
AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
QUERY = "What is Acme Ledger?"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def answer(named=False, cluster_id=0, query="q-one",
           engine="EngineA", captured_on="2026-11-01"):
    return {
        "named": named,
        "named_early": named,
        "cited": False,
        "cluster_id": cluster_id,
        "near_duplicate": False,
        "matched_aliases": [],
        "query": query,
        "engine_label": engine,
        "capture_method": "by hand",
        "captured_on": captured_on,
        "source_kind": "sampled",
        "control": False,
        "competitor_named": False,
        "citation_instances": 0,
        "self_citation_instances": 0,
        "text": "sample text",
    }


def journal_entries_with_declaration():
    entries = [
        {
            "sequence": 1,
            "entry_kind": "product_registered",
            "payload": {
                "product_id": "acme-ledger",
                "name": "Acme Ledger",
                "domain": "acme.example",
                "aliases": [],
                "competitors": [],
                "query_set": [QUERY],
            },
        },
        {
            "sequence": 2,
            "entry_kind": "round_named",
            "payload": {
                "product_id": "acme-ledger",
                "round_id": "acme-ledger:round-1",
                "round_label": "round-1",
                "importer_declaration": "all_captured",
                "supplier_relation": "independent party",
            },
        },
    ]
    for index in range(3):
        entries.append({
            "sequence": 3 + index,
            "entry_kind": "answer_imported",
            "payload": {
                "product_id": "acme-ledger",
                "round_id": "acme-ledger:round-1",
                "answer_text": "Acme Ledger tracks citations.",
                "query": QUERY,
                "engine_label_original": "Engine A",
                "engine_label_normalised": "engine a",
                "kind": "sampled",
                "captured_on": "2026-11-0%d" % (7 + index),
                "capture_method": "manual copy",
                "control_flag": False,
            },
        })
    return entries


class SeededHome(unittest.TestCase):
    def seeded_home(self, break_between_rounds=False):
        from citeline import install as install_module
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, home = root / "install", root / "home"
        install_module.install(location=str(location), home=str(home))
        service.add_product(
            home=str(home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(home), product=PRODUCT, query_set=[QUERY],
            audit_date=AUDIT_DATE)
        labels = ["round-a", "round-b"]
        for position, label in enumerate(labels):
            if break_between_rounds and position == 1:
                service.set_category(
                    home=str(home), product=PRODUCT,
                    category_terms=["citation software"],
                    audit_date=AUDIT_DATE)
            service.name_round(
                home=str(home), product=PRODUCT, round_label=label,
                importer_declaration="all captured",
                supplier_relation="independent party",
                audit_date=AUDIT_DATE)
            service.probe_import(
                home=str(home),
                answer_file=os.path.join(FIXTURES, "w4-repro-a1.txt"),
                product=PRODUCT, round=label,
                engine_label="Engine A", query=QUERY,
                kind="real_sample", captured_on="2026-11-07",
                capture_method="manual copy", audit_date=AUDIT_DATE)
        return home


class TestD02DeclarationReachesFrame(SeededHome):
    def test_journal_route_carries_declaration_into_frame(self):
        result = metrics.round_metrics_from_journal(
            journal_entries_with_declaration(), detector_version=1)
        frame = field(result, "sampling_frame")
        self.assertEqual(
            field(frame, "importer_declaration"), "all_captured")
        self.assertIs(field(frame, "declaration_unverifiable"), True)
        self.assertEqual(field(frame, "imported_count"), 3)

    def test_service_probe_report_frame_carries_declaration(self):
        home = self.seeded_home()
        report = service.probe_report(
            home=str(home), product=PRODUCT, round="round-a",
            form="advanced", audit_date=AUDIT_DATE)
        body = report.get("report", report) \
            if isinstance(report, dict) else report
        frame = field(body, "sampling_frame")
        self.assertEqual(
            field(frame, "importer_declaration"), "all_captured")

    def test_service_trend_round_frames_carry_declaration(self):
        home = self.seeded_home()
        trend = service.probe_trend(
            home=str(home), product=PRODUCT, round_a="round-a",
            round_b="round-b", form="advanced", audit_date=AUDIT_DATE)
        for key in ("first_round", "second_round"):
            frame = field(field(trend, key), "sampling_frame")
            self.assertEqual(
                field(frame, "importer_declaration"), "all_captured",
                key)


class TestD05DominanceSingleAxis(unittest.TestCase):
    def test_single_engine_at_100_percent_reports_dominance(self):
        answers = [
            answer(named=True, cluster_id=0, query="q-one",
                   captured_on="2026-11-01"),
            answer(named=True, cluster_id=1, query="q-two",
                   captured_on="2026-11-02"),
            answer(named=True, cluster_id=2, query="q-three",
                   captured_on="2026-11-03"),
        ]
        result = metrics.round_metrics(answers, "sampled")
        composition = field(result, "composition")
        self.assertEqual(
            field(composition, "largest_engine_share_count"), 3)
        self.assertAlmostEqual(
            field(composition, "largest_engine_share_percent"),
            100.0, places=4)
        self.assertTrue(field(composition, "dominance_note"))

    def test_single_engine_and_query_at_100_percent_reports(self):
        answers = [
            answer(named=True, cluster_id=i,
                   captured_on="2026-11-0%d" % (1 + i))
            for i in range(3)
        ]
        result = metrics.round_metrics(answers, "sampled")
        composition = field(result, "composition")
        self.assertTrue(field(composition, "dominance_note"))

    def test_no_axis_over_half_reports_no_dominance(self):
        answers = [
            answer(named=True, cluster_id=0, query="q-one",
                   engine="EngineA", captured_on="2026-11-01"),
            answer(named=True, cluster_id=1, query="q-one",
                   engine="EngineB", captured_on="2026-11-01"),
            answer(named=True, cluster_id=2, query="q-two",
                   engine="EngineA", captured_on="2026-11-02"),
            answer(named=True, cluster_id=3, query="q-two",
                   engine="EngineB", captured_on="2026-11-02"),
        ]
        result = metrics.round_metrics(answers, "sampled")
        composition = field(result, "composition")
        self.assertFalse(field(composition, "dominance_note"))


class TestD23TrendHonestySentence(SeededHome):
    def test_advanced_trend_carries_honesty_sentence(self):
        home = self.seeded_home()
        trend = service.probe_trend(
            home=str(home), product=PRODUCT, round_a="round-a",
            round_b="round-b", form="advanced", audit_date=AUDIT_DATE)
        self.assertEqual(
            trend.get("honesty_sentence"), HONESTY_SENTENCE)
        for key in ("first_round", "second_round"):
            self.assertEqual(
                field(trend, key).get("honesty_sentence"),
                HONESTY_SENTENCE, key)

    def test_advanced_trend_on_series_break_carries_sentence(self):
        home = self.seeded_home(break_between_rounds=True)
        trend = service.probe_trend(
            home=str(home), product=PRODUCT, round_a="round-a",
            round_b="round-b", form="advanced", audit_date=AUDIT_DATE)
        self.assertTrue(field(trend, "series_break"))
        self.assertEqual(
            trend.get("honesty_sentence"), HONESTY_SENTENCE)
        for key in ("first_round", "second_round"):
            self.assertEqual(
                field(trend, key).get("honesty_sentence"),
                HONESTY_SENTENCE, key)


if __name__ == "__main__":
    unittest.main()
