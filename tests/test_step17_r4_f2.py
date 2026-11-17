"""Registry and acquisition.

Test first pins for register, and. Each test reproduces the
defect named at its register entry, then stands as the pin for
its cure."""

import os
import tempfile
import time
import unittest

from citeline import acquisition, journal, registry

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

    def extract(self, name, content):
        path = self.write_page(name, content)
        return acquisition.extract_page(
            self.home, product_id="p-example", page_path=path,
            audit_date=AUDIT_DATE)


class TestS17R4010StructureScanCost(Base):
    def test_fragment_scan_costs_linear_time_at_scale(self):
        text = "<p>hello world</p>" * 60000
        start = time.perf_counter()
        acquisition._leading_structure(text)
        elapsed = time.perf_counter() - start
        self.assertLess(
            elapsed, 4.0,
            "structure scan took %.3f seconds" % elapsed)

    def test_dense_fragment_scan_costs_linear_time_at_scale(self):
        text = "<p></p>" * 150000
        start = time.perf_counter()
        acquisition._leading_structure(text)
        elapsed = time.perf_counter() - start
        self.assertLess(
            elapsed, 4.0,
            "dense structure scan took %.3f seconds" % elapsed)


class TestS17R4011TagEndQuotes(Base):
    def test_scan_tag_end_ignores_quote_in_unquoted_value(self):
        text = "<div data-note=don't><html>"
        self.assertEqual(acquisition._scan_tag_end(text, 0), 20)

    def test_xhtml_root_after_unquoted_apostrophe_tag_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "a.html",
                "<div data-note=don't>" + XHTML_ROOT +
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_xhtml_root_after_unquoted_double_quote_tag_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "b.html",
                '<div data-note=a"b>' + XHTML_ROOT +
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_xhtml_root_tag_own_unquoted_apostrophe_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "c.html",
                "<html data-note=don't "
                'xmlns="http://www.w3.org/1999/xhtml">'
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_furniture_skipper_reads_unquoted_apostrophe(self):
        detected = acquisition.detect_format(
            "<!foo bar=a'b><html><body><p>Real text here.</p>"
            "</body></html>", filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")

    def test_quoted_value_still_holds_tag_open(self):
        text = '<div data-note="don\'t"><html>'
        self.assertEqual(acquisition._scan_tag_end(text, 0), 22)


class TestS17R4012RootNamespaceDecoded(Base):
    def test_decimal_entity_namespace_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "a.html",
                '<html xmlns="http:&#47;&#47;www.w3.org&#47;'
                '1999&#47;xhtml"><body><p>Real text here.</p>'
                "</body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_hex_entity_namespace_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "b.html",
                '<html xmlns="http:&#x2f;&#x2f;www.w3.org&#x2f;'
                '1999&#x2f;xhtml"><body><p>Real text here.</p>'
                "</body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_local_part_entity_namespace_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "c.html",
                '<html xmlns="http://www.w3.org/1999/xhtm&#108;">'
                "<body><p>Real text here.</p></body></html>")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestS17R4013ContentProbeForms(Base):
    def test_missing_element_forms_detect_as_html(self):
        tags = ("meta", "link", "base", "input", "source", "track",
                "col", "area", "colgroup", "tfoot", "search", "data",
                "meter", "progress", "output", "slot", "ruby", "samp",
                "var", "dfn", "bdi", "bdo", "del", "ins", "datalist",
                "optgroup", "option", "map")
        for tag in tags:
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    '<%s x="1"><p>hello content here</p>' % tag,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_meta_led_document_detects_as_html(self):
        detected = acquisition.detect_format(
            '<meta charset="utf-8"><html><body><p>Real text '
            "here.</p></body></html>", filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")

    def test_link_led_document_detects_as_html(self):
        detected = acquisition.detect_format(
            '<link rel="stylesheet" href="x.css"><html><body>'
            "<p>Real text here.</p></body></html>",
            filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")

    def test_bogus_processing_instruction_steps_over(self):
        detected = acquisition.detect_format(
            "<?foo bar><p>hello content here</p>",
            filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")


class TestS17R4014RegistryCycleAtomic(Base):
    def _correct(self, sequence, corrected_record):
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": sequence,
             "corrected_record": corrected_record},
            audit_date=AUDIT_DATE)

    def test_register_page_rejudges_after_correction_lands(self):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        snap_entry = entries[-1]
        corrected = dict(snap_entry["payload"])
        corrected["snapshot_id"] = "snap-corrected-9"
        original = registry._snapshots
        fired = []

        def hooked(home):
            result = original(home)
            if not fired:
                fired.append(True)
                self._correct(snap_entry["sequence"], corrected)
            return result

        registry._snapshots = hooked
        try:
            with self.assertRaises(registry.RegistryError):
                registry.register_page(
                    self.home, "P2", snapshot="snap-2",
                    audit_date=AUDIT_DATE)
        finally:
            registry._snapshots = original
        standing = registry.register_page(
            self.home, "P2", snapshot="snap-corrected-9",
            audit_date=AUDIT_DATE)
        self.assertEqual(standing["snapshot_id"], "snap-corrected-9")

    def test_name_round_rejudges_after_correction_lands(self):
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
        original = registry._rounds
        fired = []

        def hooked(home):
            result = original(home)
            if not fired:
                fired.append(True)
                self._correct(round_entry["sequence"], corrected)
            return result

        registry._rounds = hooked
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.name_round(
                    self.home, "Prod", round_label="NewLabel",
                    importer_declaration=(
                        "all captured answers imported"),
                    supplier_relation=(
                        "supplied by the audited party"),
                    audit_date=AUDIT_DATE)
            self.assertEqual(_token(caught.exception),
                             "ROUND_LABEL_EXISTS")
        finally:
            registry._rounds = original


class TestS17R4015MarkerInCorrectedRecord(Base):
    def test_marker_resolves_against_replaced_sequence(self):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        snap_entry = entries[-1]
        self.assertEqual(snap_entry["sequence"], 2)
        corrected = dict(snap_entry["payload"])
        corrected["snapshot_id"] = "snap-{sequence}"
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": snap_entry["sequence"],
             "corrected_record": corrected},
            audit_date=AUDIT_DATE)
        stored = journal.fold(self.home)[-1]["payload"]
        self.assertEqual(
            stored["corrected_record"]["snapshot_id"], "snap-2")
        ids = [s["snapshot_id"] for s in registry._snapshots(self.home)]
        self.assertEqual(ids, ["snap-2"])


class TestS17R4016AliasNoLetterOrDigit(Base):
    def test_punctuation_alias_refused_at_add(self):
        for alias in ("!!!", "---", "***", "?!.", "___", "...", "((("):
            with self.subTest(alias=alias):
                with self.assertRaises(registry.RegistryError) as caught:
                    self.add(name="Prod %s" % abs(hash(alias)),
                             aliases=[alias])
                self.assertEqual(_token(caught.exception),
                                 "VALIDATION_FAILED")

    def test_punctuation_alias_refused_at_set_aliases(self):
        self.add()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_aliases(
                self.home, "Example Product", ["!!!"],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_punctuation_competitor_alias_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[{
                "name": "Rival", "domain": "rival.com",
                "aliases": ["---"]}])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_alias_with_a_letter_still_admitted(self):
        record = self.add(aliases=["Pro! duct", "abc"])
        self.assertEqual(record["aliases"], ["Pro! duct", "abc"])


class TestS17R4062FrontMatterValueReading(Base):
    def _front(self, block_lines, value_limit=10):
        notes = []
        text = "---\n" + "\n".join(block_lines) + "\n---\nbody text\n"
        return acquisition._front_matter(
            text, "markdown", notes, value_limit=value_limit)

    def test_comment_line_is_no_value(self):
        result = self._front(
            ["# note: " + "x" * 100, "title: short"])
        self.assertEqual(result, "body text")

    def test_continuation_accumulates_into_value(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self._front(["title: 12345678", "  90abcdef"])
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_single_line_value_over_limit_still_refused(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self._front(["title: " + "x" * 20])
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_short_value_with_continuation_within_limit_passes(self):
        result = self._front(["title: abc", "  de"])
        self.assertEqual(result, "body text")


class TestS17R4071MarkerThroughListUnderIdentityKey(Base):
    def test_marker_in_list_under_identity_key_resolves(self):
        journal.append_entry(
            self.home, "failure_record",
            {"answer_id": ["ans-{sequence}", "plain"],
             "run_id": "run-{sequence}"},
            audit_date=AUDIT_DATE)
        payload = journal.fold(self.home)[-1]["payload"]
        self.assertEqual(payload["answer_id"], ["ans-1", "plain"])
        self.assertEqual(payload["run_id"], "run-1")

    def test_marker_in_nested_list_under_identity_key_resolves(self):
        journal.append_entry(
            self.home, "failure_record",
            {"snapshot_id": [["snap-{sequence}"]]},
            audit_date=AUDIT_DATE)
        payload = journal.fold(self.home)[-1]["payload"]
        self.assertEqual(payload["snapshot_id"], [["snap-1"]])


if __name__ == "__main__":
    unittest.main()
