"""Step 20 fix seat FX20-03 tests.

Pins for register items S20-04, S20-05, S20-06, and S20-27.
Written before the cures they pin. The S20-04 cost test is a
cost bound test: its result stands read as a measurement
under the standing carve out for cost bound tests, not as a
logic verdict. Dates are call inputs in every test.
Copyright: J.P. Picard aka Macro-Harder.
"""

import inspect
import tempfile
import time
import unittest
from pathlib import Path

from citeline import probe_import as import_module
from citeline import service
from citeline import install as install_module

AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
ROUND = "round-1"


def token_of(exc):
    return getattr(exc, "error_value", None) or getattr(
        exc, "token", None) or ""


def sheet_text(bodies, kinds=None, dates=None):
    lines = [
        "Citeline capture worksheet",
        "product: " + PRODUCT,
        "round: " + ROUND,
        "queries to attempt:",
        "query: " + Q1,
        "engine labels to attempt:",
        "engine: Engine A",
        "slots to fill by hand, one answer per slot:",
        "| slot | answer text stands below its slot line |",
    ]
    for index, body in bodies.items():
        captured = (dates or {}).get(index, "2026-11-10")
        kind = (kinds or {}).get(index, "real_sample")
        lines.append(
            "slot %d: query= %s engine_label= Engine A "
            "kind= %s captured_on= %s "
            "capture_method= manual copy" % (index, Q1, kind, captured))
        lines.extend(body.split("\n"))
    return "\n".join(lines) + "\n"


class ImportBase(unittest.TestCase):
    def temp_file(self, data, name="answer.txt"):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / name
        path.write_text(data, encoding="utf-8")
        return path

    def prepare_sheet(self, path, **extra):
        kwargs = {
            "answer_file": str(path), "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1],
        }
        kwargs.update(extra)
        return import_module.prepare_worksheet_import(**kwargs)


def standing_controls(kind, count):
    return [{
        "kind": kind,
        "engine_label_normalised": "engine a",
        "query": Q1,
        "content_hash": "hash-%s-%d" % (kind, index),
        "captured_on": "2026-11-0%d" % (index + 1),
        "control_flag": True,
    } for index in range(count)]


class TestS2004SlotParseCost(ImportBase):
    def test_slot_line_long_space_run_inside_bound(self):
        line = "slot 1:" + " " * 4000 + "x"
        start = time.monotonic()
        parsed = import_module._parse_slot_line(line)
        elapsed = time.monotonic() - start
        self.assertIsNone(parsed)
        self.assertLess(elapsed, 2.0)

    def test_valid_slot_line_long_space_run_inside_bound(self):
        line = (
            "slot 1: query= " + Q1 + " " * 4000
            + "engine_label= Engine A kind= real_sample "
            "captured_on= 2026-11-10 capture_method= manual copy")
        start = time.monotonic()
        parsed = import_module._parse_slot_line(line)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 2.0)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["fields"]["query"], Q1)
        self.assertEqual(parsed["fields"]["engine_label"], "Engine A")
        self.assertEqual(parsed["fields"]["kind"], "real_sample")
        self.assertEqual(parsed["fields"]["captured_on"], "2026-11-10")
        self.assertEqual(parsed["fields"]["capture_method"], "manual copy")

    def test_slot_line_separator_dressings_still_read(self):
        line = (
            "slot 1: query= " + Q1 + "  engine_label= Engine A "
            "ki\ufeffnd= real_sample captured_on= 2026-11-10 "
            "capture_method= manual copy")
        parsed = import_module._parse_slot_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["fields"]["query"], Q1)
        self.assertEqual(parsed["fields"]["engine_label"], "Engine A")
        self.assertEqual(parsed["fields"]["kind"], "real_sample")


class TestS2005WorksheetControlCapPerKind(ImportBase):
    def test_other_kind_controls_do_not_bar_worksheet_control(self):
        path = self.temp_file(sheet_text({1: "A real sample answer."}))
        records = self.prepare_sheet(
            path, standing_records=standing_controls("fixture", 5),
            control_count=5, control_designation="positive")
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["control_flag"])

    def test_same_kind_controls_still_bar_worksheet_control(self):
        path = self.temp_file(sheet_text({1: "A real sample answer."}))
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, standing_records=standing_controls("real_sample", 5),
                control_count=5, control_designation="positive")
        self.assertEqual(token_of(caught.exception),
                         "CONTROL_CAP_EXCEEDED")

    def test_mixed_kind_sheet_counts_controls_per_kind(self):
        bodies = {}
        kinds = {}
        dates = {}
        for index in range(1, 7):
            bodies[index] = "Sheet answer number %d standing here." % index
            kinds[index] = "fixture" if index % 2 else "real_sample"
            dates[index] = "2026-11-0%d" % index
        path = self.temp_file(sheet_text(bodies, kinds=kinds, dates=dates))
        records = self.prepare_sheet(path, control_designation="positive")
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record["control_flag"] for record in records))

    def test_service_worksheet_route_counts_per_kind(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, home = root / "install", root / "home"
        install_module.install(location=str(location), home=str(home))
        service.add_product(
            home=str(home), name="p-alpha",
            canonical_line="p-alpha line.", domain="example.com",
            audit_date=AUDIT_DATE)
        service.set_query_set(home=str(home), product="p-alpha",
                              query_set=[Q1], audit_date=AUDIT_DATE)
        service.name_round(home=str(home), product="p-alpha",
                           round_label=ROUND,
                           importer_declaration="operator",
                           supplier_relation="first party",
                           audit_date=AUDIT_DATE)
        for index in range(5):
            answer = root / ("fixture-%d.txt" % index)
            answer.write_text(
                "Fixture control answer %d standing here.\n" % index,
                encoding="utf-8")
            service.probe_import(
                home=str(home), answer_file=str(answer),
                product="p-alpha", round=ROUND,
                engine_label="engine-a", query=Q1, kind="fixture",
                captured_on="2026-11-0%d" % (index + 1),
                capture_method="manual copy",
                control_designation="positive", audit_date=AUDIT_DATE)
        sheet = root / "sheet.txt"
        sheet.write_text(
            "Citeline capture worksheet\n"
            "product: p-alpha\n"
            "round: " + ROUND + "\n"
            "queries to attempt:\n"
            "query: " + Q1 + "\n"
            "engine labels to attempt:\n"
            "engine: engine-a\n"
            "slots to fill by hand, one answer per slot:\n"
            "| slot | answer text stands below its slot line |\n"
            "slot 1: query= " + Q1 + " engine_label= engine-a "
            "kind= real_sample captured_on= 2026-11-10 "
            "capture_method= manual copy\n"
            "A real sample control answer standing here.\n",
            encoding="utf-8")
        result = service.probe_import(
            home=str(home), answer_file=str(sheet), product="p-alpha",
            round=ROUND, engine_label="engine-a", query=Q1,
            kind="real_sample", captured_on="2026-11-10",
            capture_method="manual copy",
            control_designation="positive", audit_date=AUDIT_DATE)
        self.assertIsNotNone(result)


class TestS2006NulPathGoverned(ImportBase):
    def adapter_kwargs(self, answer_file):
        return {
            "answer_file": answer_file, "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1],
        }

    def test_adapter_nul_path_refused_in_vocabulary(self):
        with self.assertRaises(
                import_module.ProbeImportError) as caught:
            import_module.probe_import(
                **self.adapter_kwargs("bad\x00path.txt"))
        self.assertEqual(token_of(caught.exception),
                         "SUPPLIED_PATH_UNSAFE")

    def test_read_answer_file_nul_path_refused_in_vocabulary(self):
        with self.assertRaises(
                import_module.ProbeImportError) as caught:
            import_module.read_answer_file("bad\x00path.txt")
        self.assertEqual(token_of(caught.exception),
                         "SUPPLIED_PATH_UNSAFE")

    def test_worksheet_prepare_nul_path_refused_in_vocabulary(self):
        with self.assertRaises(
                import_module.ProbeImportError) as caught:
            import_module.prepare_worksheet_import(
                **self.adapter_kwargs("bad\x00sheet.txt"))
        self.assertEqual(token_of(caught.exception),
                         "SUPPLIED_PATH_UNSAFE")


class TestS2027CommentsDuplicateOnly(unittest.TestCase):
    def test_worksheet_preparation_comments_state_no_contradiction(self):
        source = inspect.getsource(
            import_module.prepare_worksheet_import)
        self.assertNotIn("contradiction", source)


if __name__ == "__main__":
    unittest.main()
