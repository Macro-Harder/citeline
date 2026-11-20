"""Registry and acquisition.

Test first pins for register, and. Each test reproduces the
defect named under the settled rule against the governing brief
or plan text cited there, then stands as the pin for its cure."""

import hashlib
import json
import multiprocessing
import os
import tempfile
import time
import unittest

from citeline import acquisition, journal, registry

AUDIT_DATE = "2026-11-14"


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

    def fresh_home(self, label):
        home = os.path.join(self.tmp.name, label)
        os.makedirs(home)
        return home

    def add(self, home=None, name="Example Product", **kwargs):
        kwargs.setdefault("canonical_line", "A line.")
        kwargs.setdefault("domain", "example.com")
        kwargs.setdefault("audit_date", AUDIT_DATE)
        return registry.add_product(home or self.home, name=name,
                                    **kwargs)


class TestS17R2008NfcAddress(RegistryBase):
    def test_decomposed_spelling_resolves_standing_product(self):
        self.add(name="Caf\u00e9")
        record = registry.get_product(self.home, "Cafe\u0301")
        self.assertIsNotNone(record)
        self.assertEqual(record["name"], "Caf\u00e9")
        found = registry.find_product(self.home, "Cafe\u0301")
        self.assertIsNotNone(found)
        self.assertEqual(found["product_id"], record["product_id"])

    def test_set_operations_addressed_by_decomposed_spelling(self):
        self.add(name="Caf\u00e9")
        updated = registry.set_aliases(
            self.home, "Cafe\u0301", ["cafe alias"],
            audit_date=AUDIT_DATE)
        self.assertEqual(updated["aliases"], ["cafe alias"])
        updated = registry.set_query_set(
            self.home, "Cafe\u0301", ["cafe query"],
            audit_date=AUDIT_DATE)
        self.assertEqual(updated["query_set"], ["cafe query"])
        record = registry.get_product(self.home, "Caf\u00e9")
        self.assertEqual(record["aliases"], ["cafe alias"])
        self.assertEqual(record["query_set"], ["cafe query"])


class TestS17R2009CompetitorEmptySlug(RegistryBase):
    def test_punctuation_only_competitor_is_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[{
                "name": "!!!", "domain": "x.com", "aliases": []}])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_non_latin_only_competitor_is_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(competitors=[{
                "name": "\u88fd\u54c1", "domain": "x.com",
                "aliases": []}])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_whitespace_only_competitor_is_refused_at_set(self):
        self.add(competitors=[{
            "name": "Standing Rival", "domain": "rival.com",
            "aliases": []}])
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_competitors(
                self.home, "Example Product",
                [{"name": "   ", "domain": "x.com", "aliases": []}],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        record = registry.get_product(self.home, "Example Product")
        self.assertEqual(
            [c["name"] for c in record["competitors"]],
            ["Standing Rival"])
        self.assertEqual(
            [c["competitor_id"] for c in record["competitors"]],
            ["c-standing-rival"])


class TestS17R2010QuerySetSurrogate(RegistryBase):
    def test_surrogate_query_is_refused_at_set(self):
        self.add()
        registry.set_query_set(
            self.home, "Example Product", ["standing query"],
            audit_date=AUDIT_DATE)
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_query_set(
                self.home, "Example Product", ["bad\ud800query"],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(caught.exception.row, "X-5")
        self.assertEqual(caught.exception.exit_code, 2)
        record = registry.get_product(self.home, "Example Product")
        self.assertEqual(record["query_set"], ["standing query"])

    def test_surrogate_query_is_refused_at_add(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(query_set=["bad\ud800q"])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])


class AcquisitionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def write_page(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def extract(self, path):
        return acquisition.extract_page(
            self.home, product_id="p-example", page_path=path,
            audit_date=AUDIT_DATE)

    def assert_extraction_fails(self, name, content):
        path = self.write_page(name, content)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(path)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestS17R2011QuotedSelfClose(AcquisitionBase):
    def test_script_with_quoted_self_close_spelling_fails(self):
        self.assert_extraction_fails(
            "q1.html",
            "<html><body><p>Before text here.</p>"
            "<script data-x=\"/>\">var x=1;"
            "<p>After swallowed text here.</p></body></html>")

    def test_style_with_quoted_self_close_spelling_fails(self):
        self.assert_extraction_fails(
            "q2.html",
            "<html><body><p>Before text here.</p>"
            "<style data-x=\"/>\">.a { color: red; }"
            "<p>After swallowed text here.</p></body></html>")


class TestS17R2012CommentForms(AcquisitionBase):
    def test_bang_closed_comment_does_not_shield_unclosed_script(self):
        self.assert_extraction_fails(
            "c1.html",
            "<html><body><!-- </script> --!><p>Before text.</p>"
            "<script>var x=1;<p>After swallowed text here.</p>"
            "</body></html>")

    def test_abruptly_closed_comment_does_not_shield_script(self):
        for index, spelling in enumerate(("<!-->", "<!--->")):
            with self.subTest(spelling=spelling):
                self.assert_extraction_fails(
                    "c2-%d.html" % index,
                    "<html><body>" + spelling + "<p>Before text.</p>"
                    "<script>var x=1;<p>After swallowed text here.</p>"
                    "</body></html>")

    def test_comment_opening_inside_attribute_is_not_a_comment(self):
        self.assert_extraction_fails(
            "c3.html",
            "<html><body><p title=\"<!--\">x</p> </script>"
            "<script>var x=1;<p>After swallowed text here.</p>"
            "</body></html>")

    def test_comment_shape_inside_script_body_fails_closed(self):
        self.assert_extraction_fails(
            "c4.html",
            "<html><body><script><!-- </script> --></script>"
            "<p>Real text here.</p></body></html>")


class TestS17R2013ClosingSpellings(AcquisitionBase):
    def test_script_closed_with_slash_spelling_extracts(self):
        path = self.write_page(
            "s1.html",
            "<html><body><script>var x=1;</script/>"
            "<p>Real text here.</p></body></html>")
        result = self.extract(path)
        self.assertIn("Real text here.",
                      result["extracted"]["running_text"])

    def test_script_closed_with_attribute_spelling_extracts(self):
        path = self.write_page(
            "s2.html",
            "<html><body><script>var x=1;</script foo>"
            "<p>Real text here.</p></body></html>")
        result = self.extract(path)
        self.assertIn("Real text here.",
                      result["extracted"]["running_text"])


class TestS17R2014ContentProbeCost(AcquisitionBase):
    def test_unmatched_brackets_detect_within_bound(self):
        path = self.write_page(
            "brackets.md", "[" * 40000 + "\n\nBody text here.\n")
        start = time.monotonic()
        result = self.extract(path)
        elapsed = time.monotonic() - start
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")
        self.assertLess(elapsed, 2.0)

    def test_link_prefix_units_detect_within_bound(self):
        path = self.write_page(
            "links.md", "[a](x" * 20000 + "\n\nBody text here.\n")
        start = time.monotonic()
        result = self.extract(path)
        elapsed = time.monotonic() - start
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")
        self.assertLess(elapsed, 2.0)

    def test_image_prefix_units_detect_within_bound(self):
        path = self.write_page(
            "images.md", "![a](x" * 12000 + "\n\nBody text here.\n")
        start = time.monotonic()
        result = self.extract(path)
        elapsed = time.monotonic() - start
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")
        self.assertLess(elapsed, 2.0)


class TestS17R2015ContainerQuotedBracket(AcquisitionBase):
    def test_namespace_behind_quoted_bracket_fails(self):
        self.assert_extraction_fails(
            "x1.html",
            "<html data-x=\"a>b\" "
            "xmlns=\"http://www.w3.org/1999/xhtml\">"
            "<body><p>Body text here.</p></body></html>")

    def test_doctype_word_behind_quoted_bracket_fails(self):
        self.assert_extraction_fails(
            "x2.html",
            "<!DOCTYPE html PUBLIC \"a>b XHTML 1.0\" \"x\">"
            "<html><body><p>Body text here.</p></body></html>")


class TestS17R2016FalseRootShadowing(AcquisitionBase):
    def test_commented_root_does_not_shadow_real_doctype(self):
        self.assert_extraction_fails(
            "r1.html",
            "<!-- <html> -->\n"
            "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 "
            "Strict//EN\" \"x\">"
            "<html><body><p>Body text here.</p></body></html>")

    def test_commented_root_does_not_shadow_real_root(self):
        self.assert_extraction_fails(
            "r2.html",
            "<!-- <html> -->"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\">"
            "<body><p>Body text here.</p></body></html>")

    def test_script_string_root_does_not_shadow_real_root(self):
        self.assert_extraction_fails(
            "r3.html",
            "<script>var s=\"<html>\";</script>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\">"
            "<body><p>Body text here.</p></body></html>")


class TestS17R2017MarkerInsideNonMarkup(AcquisitionBase):
    def test_doctype_spelling_inside_comment_extracts(self):
        path = self.write_page(
            "p1.html",
            "<!-- <!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0\" "
            "\"x\"> -->"
            "<html><body><p>Body text here.</p></body></html>")
        result = self.extract(path)
        self.assertIn("Body text here.",
                      result["extracted"]["running_text"])

    def test_root_spelling_inside_textarea_extracts(self):
        path = self.write_page(
            "p2.html",
            "<textarea><html xmlns=\"http://www.w3.org/1999/xhtml\">"
            "</textarea><p>Body text here.</p>")
        result = self.extract(path)
        self.assertIn("Body text here.",
                      result["extracted"]["running_text"])


class TestS17R2019ContentProbeForms(AcquisitionBase):
    def test_leading_element_forms_detect_as_html(self):
        cases = (
            ("button", "<button>Click Here</button>"
             "<p>Body paragraph text here.</p>"),
            ("textarea", "<textarea>Form body text here.</textarea>"
             "<p>Body text here.</p>"),
            ("select", "<select><option>First Option</option>"
             "</select><p>Body text.</p>"),
            ("label", "<label>Field Label</label>"
             "<p>Body paragraph text here.</p>"),
            ("iframe", "<iframe src='x.html'></iframe>"
             "<p>Body paragraph text here.</p>"),
            ("title", "<title>Page Title</title>"
             "<p>Body paragraph text here.</p>"),
            ("hgroup", "<hgroup><h1>Heading Text</h1></hgroup>"
             "<p>Body paragraph text here.</p>"),
            ("legend", "<legend>Legend Text</legend>"
             "<p>Body paragraph text here.</p>"),
            ("script", "<script>var x=1;</script>"
             "<p>Body paragraph text here.</p>"),
            ("style", "<style>.a{color:red}</style>"
             "<p>Body paragraph text here.</p>"),
        )
        for label, content in cases:
            with self.subTest(label=label):
                path = self.write_page("page-%s.txt" % label, content)
                result = self.extract(path)
                self.assertEqual(
                    result["snapshot"]["detected_format"], "html",
                    label)
                self.assertNotIn(
                    "<", result["extracted"]["running_text"], label)

    def test_comment_led_document_detects_as_html(self):
        path = self.write_page(
            "comment-led.txt",
            "<!-- site note -->\n"
            "<html><head><title>T</title></head><body>"
            "<h1>Heading Text</h1>"
            "<p>Body paragraph text here.</p></body></html>")
        result = self.extract(path)
        self.assertEqual(result["snapshot"]["detected_format"],
                         "html")
        texts = [h["text"] for h in result["extracted"]["headings"]]
        self.assertIn("Heading Text", texts)

    def test_xml_declaration_led_document_detects_as_html(self):
        path = self.write_page(
            "xml-led.txt",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<html><body><h1>Heading Text</h1>"
            "<p>Body paragraph text here.</p></body></html>")
        result = self.extract(path)
        self.assertEqual(result["snapshot"]["detected_format"],
                         "html")
        texts = [h["text"] for h in result["extracted"]["headings"]]
        self.assertIn("Heading Text", texts)


def _concurrent_extract(home, page_path, barrier, queue):
    try:
        barrier.wait(timeout=30)
        result = acquisition.extract_page(
            home, product_id="p-example", page_path=page_path,
            audit_date=AUDIT_DATE)
        queue.put(("ok", result["snapshot"]["snapshot_id"]))
    except Exception as exc:
        queue.put(("error", "%r" % (exc,)))


def _seed_journal(home, count):
    """Seed one home with a standing chained journal, built
    in the journal module's own canonical form, so the fold
    a concurrent extraction reads takes long enough for the
    appends of the other workers to land inside the window
    the round 2 attack paper ran. The seed entries are
    failure records with a long subject, standing as
    ordinary prior state."""
    payload = {
        "operation": "seed",
        "error_value": "SEED",
        "subject_identity": "s" * 1500,
        "date": AUDIT_DATE,
        "rule_fired": "SEED",
    }
    lines = []
    previous = None
    for sequence in range(1, count + 1):
        entry = {
            "sequence": sequence,
            "entry_kind": "failure_record",
            "form_version": journal.FORM_VERSION,
            "payload": dict(payload),
            "previous_hash": previous,
        }
        raw = journal.canonical_bytes(entry)
        lines.append(raw)
        previous = hashlib.sha256(raw).hexdigest()
    with open(os.path.join(home, "journal.jsonl"), "wb") as handle:
        for raw in lines:
            handle.write(raw + b"\n")


class TestS17R2082SnapshotIdentity(unittest.TestCase):
    def test_concurrent_snapshots_take_their_storing_sequence(self):
        ctx = multiprocessing.get_context("fork")
        total_stored = 0
        with tempfile.TemporaryDirectory() as tmp:
            for round_index in range(3):
                home = os.path.join(tmp, "home%d" % round_index)
                os.makedirs(home)
                _seed_journal(home, 800)
                pages = []
                for index in range(12):
                    page = os.path.join(
                        tmp, "page%d-%d.html" % (round_index, index))
                    with open(page, "w", encoding="utf-8") as handle:
                        handle.write(
                            "<html><body><p>Page body %d text "
                            "here.</p></body></html>" % index)
                    pages.append(page)
                barrier = ctx.Barrier(len(pages))
                queue = ctx.Queue()
                workers = [
                    ctx.Process(
                        target=_concurrent_extract,
                        args=(home, page, barrier, queue))
                    for page in pages]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(timeout=120)
                results = [queue.get(timeout=10) for _ in workers]
                succeeded = sorted(
                    value for status, value in results
                    if status == "ok")
                for status, value in results:
                    if status != "ok":
                        # A contended extraction fails honestly
                        # and stores nothing; the break under
                        # test is in the identities of the
                        # stored ones.
                        self.assertIn("already holds", value)
                stored = {}
                journal_path = os.path.join(home, "journal.jsonl")
                with open(journal_path, encoding="utf-8") as handle:
                    for line in handle:
                        entry = json.loads(line)
                        if entry.get("entry_kind") != \
                                "snapshot_registered":
                            continue
                        payload = entry["payload"]
                        stored[payload["snapshot_id"]] = \
                            entry["sequence"]
                        self.assertEqual(
                            payload["snapshot_id"],
                            "snap-%d" % entry["sequence"],
                            "round %d" % round_index)
                self.assertEqual(len(stored), len(succeeded),
                                 "round %d" % round_index)
                self.assertEqual(succeeded, sorted(stored),
                                 "round %d" % round_index)
                total_stored += len(stored)
        self.assertGreaterEqual(total_stored, 2)


class TestS17R2098RegistryLockForm(RegistryBase):
    def test_lock_path_as_directory_fails_in_vocabulary_at_add(self):
        os.makedirs(os.path.join(self.home, ".citeline-registry.lock"))
        with self.assertRaises(registry.RegistryError) as caught:
            self.add()
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_lock_path_as_directory_fails_in_vocabulary_at_set(self):
        self.add()
        lock_path = os.path.join(self.home, ".citeline-registry.lock")
        if os.path.isfile(lock_path):
            os.remove(lock_path)
        os.makedirs(lock_path)
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_aliases(
                self.home, "Example Product", ["some alias"],
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
