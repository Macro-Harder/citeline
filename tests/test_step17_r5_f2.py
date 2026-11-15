"""Step 17 round 5 fix seat F2 tests, registry and acquisition.

Test first pins for register entries S17-R5-005 to
S17-R5-011 and S17-R5-064. Each test reproduces the
defect named at its register entry, then stands as the
pin for its cure.
"""

import os
import tempfile
import unittest

from citeline import acquisition, errors, journal, probe_import
from citeline import registry, service, watch

AUDIT_DATE = "2026-11-14"
XHTML_ROOT = '<html xmlns="http://www.w3.org/1999/xhtml"></html>'


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name="Example Product", **kwargs):
        kwargs.setdefault("canonical_line", "A line.")
        kwargs.setdefault("domain", "example.com")
        kwargs.setdefault("audit_date", AUDIT_DATE)
        return registry.add_product(self.home, name=name, **kwargs)

    def write_page(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def extract(self, name, content, product_id="p-example"):
        path = self.write_page(name, content)
        return acquisition.extract_page(
            self.home, product_id=product_id, page_path=path,
            audit_date=AUDIT_DATE)

    def correct(self, sequence, corrected_record):
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": sequence,
             "corrected_record": corrected_record},
            audit_date=AUDIT_DATE)


class TestR5_005TagEndEqualsForms(Base):
    def test_stray_equals_tag_ends_where_the_parser_ends_it(self):
        text = '<div a="x" = "y>' + XHTML_ROOT
        self.assertEqual(
            acquisition._scan_tag_end(text, 0), text.index(">"))

    def test_missing_value_tag_ends_where_the_parser_ends_it(self):
        text = "<div a='x' b= 'y>" + XHTML_ROOT
        self.assertEqual(
            acquisition._scan_tag_end(text, 0), text.index(">"))

    def test_xhtml_root_after_stray_equals_tag_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "a.html",
                '<div a="x" = "y>' + XHTML_ROOT +
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_xhtml_root_after_missing_value_tag_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "b.html",
                "<div a='x' b= 'y>" + XHTML_ROOT +
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_quoted_value_holding_a_bracket_still_holds(self):
        text = '<div a="x>y"><html>'
        self.assertEqual(
            acquisition._scan_tag_end(text, 0),
            len('<div a="x>y">') - 1)


class TestR5_006RegistryCycleFinalWindow(Base):
    def _seed_snapshot(self):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        return entries[-1]

    def _wrap_append_with_correction(self, kind, sequence, corrected):
        original = journal.append_entry
        state = {"fired": False, "contended": []}

        def hooked(home, entry_kind, payload, **kwargs):
            if entry_kind == kind and not state["fired"]:
                state["fired"] = True
                try:
                    original(
                        home, "correction",
                        {"supersedes_sequence": sequence,
                         "corrected_record": corrected},
                        audit_date=AUDIT_DATE)
                except Exception as exc:
                    state["contended"].append(exc)
            return original(home, entry_kind, payload, **kwargs)

        journal.append_entry = hooked
        return original, state

    def test_register_page_final_window_correction_cannot_land(self):
        snap_entry = self._seed_snapshot()
        corrected = dict(snap_entry["payload"])
        corrected["snapshot_id"] = "snap-corrected-9"
        original, state = self._wrap_append_with_correction(
            "snapshot_registered", snap_entry["sequence"], corrected)
        try:
            result = registry.register_page(
                self.home, "P2", snapshot="snap-2",
                audit_date=AUDIT_DATE)
        finally:
            journal.append_entry = original
        self.assertTrue(state["fired"])
        self.assertEqual(len(state["contended"]), 1)
        self.assertEqual(result["snapshot_id"], "snap-2")
        standing = registry._snapshots(self.home)
        self.assertEqual(
            [item["snapshot_id"] for item in standing], ["snap-2"])
        self.assertTrue(standing[0]["is_product_page"])

    def test_name_round_final_window_correction_cannot_land(self):
        self.add(name="Prod")
        registry.name_round(
            self.home, "Prod", round_label="OldLabel",
            importer_declaration="all captured answers imported",
            supplier_relation="supplied by the audited party",
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        round_entry = entries[-1]
        corrected = dict(round_entry["payload"])
        corrected["round_label"] = "NewLabel"
        corrected["round_id"] = "p-prod:NewLabel"
        original, state = self._wrap_append_with_correction(
            "round_named", round_entry["sequence"], corrected)
        try:
            registry.name_round(
                self.home, "Prod", round_label="NewLabel",
                importer_declaration="all captured answers imported",
                supplier_relation="supplied by the audited party",
                audit_date=AUDIT_DATE)
        finally:
            journal.append_entry = original
        self.assertTrue(state["fired"])
        self.assertEqual(len(state["contended"]), 1)
        labels = [item["round_label"]
                  for item in registry._rounds(self.home)]
        self.assertEqual(labels, ["OldLabel", "NewLabel"])

    def test_setter_final_window_correction_cannot_land(self):
        self.add(name="Prod", aliases=["alpha"])
        entries = journal.fold(self.home)
        product_entry = entries[-1]
        corrected = dict(product_entry["payload"])
        corrected["aliases"] = ["gamma"]
        original, state = self._wrap_append_with_correction(
            "registry_change", product_entry["sequence"], corrected)
        try:
            registry.set_aliases(
                self.home, "Prod", ["beta"], audit_date=AUDIT_DATE)
        finally:
            journal.append_entry = original
        self.assertTrue(state["fired"])
        self.assertEqual(len(state["contended"]), 1)
        record = registry.find_product(self.home, "Prod")
        self.assertEqual(record["aliases"], ["beta"])
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertNotIn("correction", kinds)

    def test_fifth_attempt_correction_is_rechecked(self):
        self.add(name="P2")
        first = self.write_page(
            "p2a.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=first,
            audit_date=AUDIT_DATE)
        second = self.write_page(
            "p2b.html",
            "<html><body><p>More real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=second,
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        snap_two = entries[1]
        snap_three = entries[2]
        original = registry._snapshots
        calls = {"count": 0}

        def hooked(home):
            result = original(home)
            calls["count"] += 1
            count = calls["count"]
            if count <= 4:
                corrected = dict(snap_two["payload"])
                corrected["snapshot_id"] = "snap-fresh-%d" % count
                self.correct(snap_two["sequence"], corrected)
            elif count == 5:
                corrected = dict(snap_three["payload"])
                corrected["snapshot_id"] = "snap-corrected-9"
                self.correct(snap_three["sequence"], corrected)
            return result

        registry._snapshots = hooked
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.register_page(
                    self.home, "P2", snapshot="snap-3",
                    audit_date=AUDIT_DATE)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")
        finally:
            registry._snapshots = original
        standing = registry._snapshots(self.home)
        by_id = {item["snapshot_id"]: item for item in standing}
        self.assertFalse(
            by_id["snap-corrected-9"]["is_product_page"])

    def test_setter_under_continuous_movement_refuses(self):
        self.add(name="Prod", aliases=["alpha"])
        original = registry._journal_version
        calls = {"count": 0}

        def hooked(home):
            result = original(home)
            calls["count"] += 1
            try:
                journal.append_entry(
                    self.home, "failure_record",
                    {"operation": "probe",
                     "error_value": "VERSION_PROBE",
                     "subject_identity": "probe-%d" % calls["count"],
                     "date": AUDIT_DATE,
                     "rule_fired": "VERSION_PROBE"},
                    audit_date=AUDIT_DATE)
            except Exception:
                pass
            return result

        registry._journal_version = hooked
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.set_aliases(
                    self.home, "Prod", ["beta"],
                    audit_date=AUDIT_DATE)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")
        finally:
            registry._journal_version = original
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertNotIn("registry_change", kinds)


class TestR5_007ContentProbeForms(Base):
    def test_doctype_whitespace_forms_detect_as_html(self):
        body = "<html><body><p>Real text here.</p></body></html>"
        for separator in ("\t", "\n", "  ", "\r\n", "\f"):
            with self.subTest(separator=repr(separator)):
                detected = acquisition.detect_format(
                    "<!DOCTYPE" + separator + "html>" + body,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_doctype_tab_form_extracts_as_html(self):
        result = self.extract(
            "page.txt",
            "<!DOCTYPE\thtml><html><body><p>Real text here.</p>"
            "</body></html>")
        self.assertEqual(result["snapshot"]["format"], "html")
        self.assertEqual(
            result["extracted"]["running_text"], "Real text here.")

    def test_remaining_element_forms_detect_as_html(self):
        for tag in ("param", "rp", "rt"):
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    '<%s x="1"><p>hello content here</p>' % tag,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_math_led_form_detects_as_html(self):
        detected = acquisition.detect_format(
            "<math><p>hello content here</p>", filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")

    def test_plain_prose_still_decides_no_format(self):
        self.assertIsNone(acquisition._content_format(
            "A plain sentence with no markup at all."))


class TestR5_008RootNamespaceDeclared(Base):
    def test_namespace_string_in_data_attribute_admits(self):
        result = self.extract(
            "a.html",
            '<html data-note="http:&#47;&#47;www.w3.org/1999/'
            'xhtml"><body><p>Real text here.</p></body></html>')
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")

    def test_namespace_string_plain_in_data_attribute_admits(self):
        result = self.extract(
            "b.html",
            '<html data-note="http://www.w3.org/1999/xhtml">'
            "<body><p>Real text here.</p></body></html>")
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")

    def test_declared_namespace_entity_spelling_still_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "c.html",
                '<html xmlns="http:&#47;&#47;www.w3.org/1999/'
                'xhtml"><body><p>Real text here.</p></body></html>')
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_declared_namespace_single_quoted_still_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "d.html",
                "<html xmlns='http://www.w3.org/1999/xhtml'>"
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_declared_namespace_unquoted_still_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "e.html",
                "<html xmlns=http://www.w3.org/1999/xhtml>"
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR5_009AliasLetterOrDigit(Base):
    FRACTION = "½"
    ROMAN = "Ⅻ"

    def test_number_only_aliases_refused_at_add(self):
        forms = (self.FRACTION * 3, self.ROMAN * 3,
                 self.FRACTION + "!!", self.ROMAN + "!!")
        for index, alias in enumerate(forms):
            with self.subTest(alias=alias):
                with self.assertRaises(registry.RegistryError) as caught:
                    self.add(name="Prod %d" % index, aliases=[alias])
                self.assertEqual(_token(caught.exception),
                                 "VALIDATION_FAILED")

    def test_number_only_alias_refused_at_set_aliases(self):
        self.add()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_aliases(
                self.home, "Example Product", [self.FRACTION * 3],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_number_only_competitor_alias_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[{
                "name": "Rival", "domain": "rival.com",
                "aliases": [self.ROMAN * 3]}])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_letter_or_digit_aliases_still_admitted(self):
        record = self.add(aliases=[
            "123", "ab!", self.FRACTION + "a!",
            self.FRACTION + "1!"])
        self.assertEqual(len(record["aliases"]), 4)


class TestR5_010QuotedContinuation(Base):
    BLOCK_LINES = None

    def _block_text(self, continuation):
        lines = ["---", "title: " + "x" * 4090, continuation,
                 "---", "body text"]
        return "\n".join(lines) + "\n"

    def test_quoted_continuation_counts_into_the_value(self):
        continuation = '  "note: ' + "y" * 20 + '"'
        notes = []
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition._front_matter(
                self._block_text(continuation), "markdown", notes)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_import_side_refuses_the_same_block(self):
        continuation = '  "note: ' + "y" * 20 + '"'
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            probe_import.extract_front_matter(
                self._block_text(continuation))
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_plain_continuation_still_counts_into_the_value(self):
        continuation = "  " + "y" * 20
        notes = []
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition._front_matter(
                self._block_text(continuation), "markdown", notes)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")


class TestR5_011LineWithNoColon(Base):
    def test_page_side_refuses_a_line_holding_no_key_and_value(self):
        text = "---\ntitle: abc\n" + "x" * 50 + "\n---\nbody text\n"
        notes = []
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition._front_matter(text, "markdown", notes)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_import_side_refuses_the_same_block(self):
        text = "---\ntitle: abc\n" + "x" * 50 + "\n---\nbody text\n"
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            probe_import.extract_front_matter(text)
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def test_indented_continuation_without_colon_still_passes(self):
        text = "---\ntitle: abc\n  continued here\n---\nbody text\n"
        notes = []
        result = acquisition._front_matter(text, "markdown", notes)
        self.assertEqual(result, "body text")


class TestR5_064UnhashableSnapshotIdentity(Base):
    def _seed_with_planted(self, snapshot_id):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        journal.append_entry(
            self.home, "snapshot_registered",
            {"snapshot_id": snapshot_id, "product_id": "p-p2",
             "is_product_page": False, "supplied_path": path},
            audit_date=AUDIT_DATE)

    def test_list_identity_refused_at_register_page(self):
        self._seed_with_planted(["snap-x"])
        with self.assertRaises(errors.CitelineError) as caught:
            service.register_page(
                home=self.home, product="P2", snapshot="snap-2",
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_dict_identity_refused_at_register_page(self):
        self._seed_with_planted({"a": 1})
        with self.assertRaises(registry.RegistryError) as caught:
            registry.register_page(
                self.home, "P2", snapshot="snap-2",
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_list_identity_refused_at_watch_coverage_count(self):
        self._seed_with_planted(["snap-x"])
        products = service.list_products(home=self.home)
        with self.assertRaises(errors.CitelineError) as caught:
            watch._standing_product_page_snapshot_count(
                self.home, products)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_clean_home_watch_coverage_count_still_answers(self):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        registry.register_page(
            self.home, "P2", snapshot="snap-2",
            audit_date=AUDIT_DATE)
        products = service.list_products(home=self.home)
        count, paths = watch._standing_product_page_snapshot_count(
            self.home, products)
        self.assertEqual(count, 1)
        self.assertEqual(len(paths), 1)


if __name__ == "__main__":
    unittest.main()
