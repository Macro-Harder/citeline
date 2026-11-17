"""Registry and acquisition.

Test first pins for register to and the registry limb of. Each
test reproduces the defect named at its register entry against
the governing text cited there, then stands as the pin for its
cure."""

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


class RegistryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, home=None, name="Example Product", **kwargs):
        kwargs.setdefault("canonical_line", "A line.")
        kwargs.setdefault("domain", "example.com")
        kwargs.setdefault("audit_date", AUDIT_DATE)
        return registry.add_product(home or self.home, name=name,
                                    **kwargs)

    def write_page(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path


class TestS17R3009MarkerConfined(RegistryBase):
    def test_marker_in_product_name_stored_as_written(self):
        returned = self.add(name="Alpha {sequence} Beta")
        self.assertEqual(returned["name"], "Alpha {sequence} Beta")
        stored = registry.get_product(
            self.home, "Alpha {sequence} Beta")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["name"], "Alpha {sequence} Beta")
        again = self.add(name="Alpha {sequence} Beta")
        self.assertEqual(again["name"], "Alpha {sequence} Beta")

    def test_marker_in_canonical_line_and_round_label_as_written(self):
        self.add(name="Plain", canonical_line="line {sequence} end")
        stored = registry.get_product(self.home, "Plain")
        self.assertEqual(stored["canonical_line"],
                         "line {sequence} end")
        named = registry.name_round(
            self.home, "Plain", round_label="Round {sequence}",
            importer_declaration="all captured answers imported",
            supplier_relation="supplied by the audited party",
            audit_date=AUDIT_DATE)
        self.assertEqual(named["round_label"], "Round {sequence}")
        rounds = registry._rounds(self.home)
        self.assertEqual(rounds[0]["round_label"], "Round {sequence}")

    def test_marker_in_snapshot_provenance_as_written(self):
        path = self.write_page(
            "page {sequence}.html",
            "<html><body><p>Real text here.</p></body></html>")
        result = acquisition.extract_page(
            self.home, product_id="p-example", page_path=path,
            audit_date=AUDIT_DATE,
            capture_method_asserted="method {sequence} end",
            evaluated_page_path="/eval/{sequence}")
        snapshot = result["snapshot"]
        self.assertTrue(
            snapshot["supplied_path"].endswith("page {sequence}.html"))
        self.assertEqual(snapshot["capture_method_asserted"],
                         "method {sequence} end")
        self.assertEqual(snapshot["evaluated_page_path"],
                         "/eval/{sequence}")
        entries = journal.fold(self.home)
        stored = entries[-1]["payload"]
        self.assertEqual(stored["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual(snapshot["snapshot_id"],
                         "snap-%d" % entries[-1]["sequence"])
        self.assertTrue(
            stored["supplied_path"].endswith("page {sequence}.html"))

    def test_identity_field_still_resolves_and_other_text_stands(self):
        journal.append_entry(
            self.home, "failure_record",
            {"run_id": "run-{sequence}",
             "subject_identity": "subject {sequence} text"},
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        payload = entries[-1]["payload"]
        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["subject_identity"],
                         "subject {sequence} text")


class TestS17R3010CommentScanCost(RegistryBase):
    def test_comment_run_costs_linear_time_in_both_scans(self):
        for spelling, closer in (("plain", "-->"), ("bang", "--!>")):
            text = ("<!-- x %s" % closer) * 20000 + (
                "<html><body><p>hi there</p></body></html>")
            for func in (acquisition._leading_structure,
                         acquisition._skip_leading_furniture):
                start = time.perf_counter()
                func(text)
                elapsed = time.perf_counter() - start
                self.assertLess(
                    elapsed, 2.0,
                    "%s scan on %s comments took %.3f seconds"
                    % (func.__name__, spelling, elapsed))


class TestS17R3011CompetitorIdentityNamespace(RegistryBase):
    def test_suffix_collision_with_natural_slug_stays_unique(self):
        record = self.add(competitors=[
            {"name": "Foo!", "domain": "a.com", "aliases": []},
            {"name": "Foo?", "domain": "b.com", "aliases": []},
            {"name": "Foo 2", "domain": "c.com", "aliases": []},
        ])
        ids = [c["competitor_id"] for c in record["competitors"]]
        self.assertEqual(len(ids), len(set(ids)))
        by_name = {c["name"]: c["competitor_id"]
                   for c in record["competitors"]}
        self.assertEqual(by_name["Foo 2"], "c-foo-2")
        self.assertEqual(by_name["Foo!"], "c-foo")

    def test_stated_competitor_id_is_not_silently_suffixed(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[
                {"name": "Foo!", "domain": "a.com", "aliases": [],
                 "competitor_id": "c-foo"},
                {"name": "Foo?", "domain": "b.com", "aliases": [],
                 "competitor_id": "c-foo"},
            ])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_suffix_collision_stays_unique_at_set_competitors(self):
        self.add()
        updated = registry.set_competitors(
            self.home, "Example Product", [
                {"name": "Foo!", "domain": "a.com", "aliases": []},
                {"name": "Foo?", "domain": "b.com", "aliases": []},
                {"name": "Foo 2", "domain": "c.com", "aliases": []},
            ], audit_date=AUDIT_DATE)
        ids = [c["competitor_id"] for c in updated["competitors"]]
        self.assertEqual(len(ids), len(set(ids)))


class TestS17R3012CorrectionsAwareRegistryReads(RegistryBase):
    def _correct(self, sequence, corrected_record):
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": sequence,
             "corrected_record": corrected_record},
            audit_date=AUDIT_DATE)

    def test_register_page_judges_by_corrected_snapshot(self):
        self.add(name="P2")
        path = self.write_page(
            "p2.html",
            "<html><body><p>Real text here.</p></body></html>")
        result = acquisition.extract_page(
            self.home, product_id="p-p2", page_path=path,
            audit_date=AUDIT_DATE)
        entries = journal.fold(self.home)
        snap_entry = entries[-1]
        corrected = dict(snap_entry["payload"])
        corrected["snapshot_id"] = "snap-corrected-9"
        self._correct(snap_entry["sequence"], corrected)
        ids = [s["snapshot_id"] for s in registry._snapshots(self.home)]
        self.assertEqual(ids, ["snap-corrected-9"])
        with self.assertRaises(registry.RegistryError):
            registry.register_page(
                self.home, "P2", snapshot="snap-2",
                audit_date=AUDIT_DATE)
        standing = registry.register_page(
            self.home, "P2", snapshot="snap-corrected-9",
            audit_date=AUDIT_DATE)
        self.assertEqual(standing["snapshot_id"], "snap-corrected-9")
        self.assertTrue(standing["is_product_page"])

    def test_name_round_judges_labels_by_corrected_fold(self):
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
        self._correct(round_entry["sequence"], corrected)
        with self.assertRaises(registry.RegistryError) as caught:
            registry.name_round(
                self.home, "Prod", round_label="NewLabel",
                importer_declaration="all captured answers imported",
                supplier_relation="supplied by the audited party",
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "ROUND_LABEL_EXISTS")
        named = registry.name_round(
            self.home, "Prod", round_label="OldLabel",
            importer_declaration="all captured answers imported",
            supplier_relation="supplied by the audited party",
            audit_date=AUDIT_DATE)
        self.assertEqual(named["round_label"], "OldLabel")


class AcquisitionBase(RegistryBase):
    def extract(self, name, content):
        path = self.write_page(name, content)
        return acquisition.extract_page(
            self.home, product_id="p-example", page_path=path,
            audit_date=AUDIT_DATE)


class TestS17R3013SelfClosingReadAsParser(AcquisitionBase):
    def test_unquoted_value_trailing_slash_opens_script(self):
        result = self.extract(
            "s1.html",
            "<script src=x/>" + XHTML_ROOT + "</script>"
            "<html><body><p>Real text here.</p></body></html>")
        self.assertEqual(result["snapshot"]["extraction_outcome"],
                         "ok")

    def test_spaced_slash_opens_script(self):
        result = self.extract(
            "s2.html",
            '<script / >var x = "' + XHTML_ROOT + '";</script>'
            "<html><body><p>Real text here.</p></body></html>")
        self.assertEqual(result["snapshot"]["extraction_outcome"],
                         "ok")


class TestS17R3014ClosingTagEndReadAsParser(AcquisitionBase):
    def test_quoted_bracket_in_closing_tag_holds_no_root(self):
        result = self.extract(
            "s3.html",
            '<script>var x=1;</script foo="a> ' + XHTML_ROOT +
            ' b"><html><body><p>Real text here.</p></body></html>')
        self.assertEqual(result["snapshot"]["extraction_outcome"],
                         "ok")


class TestS17R3015ContentProbeForms(AcquisitionBase):
    def test_leading_element_forms_detect_as_html(self):
        for tag in ("dialog", "template", "noscript", "picture",
                    "object", "embed", "menu"):
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    "<%s>hello content here</%s>" % (tag, tag),
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_bogus_declaration_led_document_detects_as_html(self):
        detected = acquisition.detect_format(
            "<!foo bar><html><body><p>Real text here.</p>"
            "</body></html>", filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")

    def test_cdata_led_document_detects_as_html(self):
        detected = acquisition.detect_format(
            "<![CDATA[ some data ]]><html><body><p>Real text "
            "here.</p></body></html>", filename="page.txt")
        self.assertEqual(detected["detected_format"], "html")


class TestS17R3057RegistryLimb(RegistryBase):
    def test_spaces_only_alias_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(aliases=["   "])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_spaces_only_alias_refused_at_set_aliases(self):
        self.add()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_aliases(
                self.home, "Example Product", ["   "],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_spaces_only_competitor_alias_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[{
                "name": "Rival", "domain": "rival.com",
                "aliases": ["   "]}])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])


if __name__ == "__main__":
    unittest.main()
