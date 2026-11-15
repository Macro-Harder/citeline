"""Step 17 round 6 fix seat F2 tests, registry and acquisition.

Test first pins for register entries S17-R6-008 to
S17-R6-015. Each test reproduces the defect named at
its register entry, then stands as the pin for its
cure.
"""

import os
import tempfile
import unittest

from citeline import acquisition, journal, probe_import, registry

AUDIT_DATE = "2026-11-14"
XHTML = "http://www.w3.org/1999/xhtml"


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

    def page_front_matter(self, block):
        text = "---\n" + block + "\n---\nbody text\n"
        notes = []
        return acquisition._front_matter(text, "markdown", notes)

    def import_front_matter(self, block):
        text = "---\n" + block + "\n---\nbody text\n"
        return probe_import.extract_front_matter(text)


class TestR6_008SelfClosedScanTerms(Base):
    def test_missing_value_form_judged_self_closed(self):
        chunk = "<script a='x' b= 'y/>"
        self.assertTrue(
            acquisition._tag_self_closed(chunk, 1 + len("script")))

    def test_stray_equals_form_judged_self_closed(self):
        chunk = '<script a="x" = "y/>'
        self.assertTrue(
            acquisition._tag_self_closed(chunk, 1 + len("script")))

    def test_missing_value_forms_refuse_the_xhtml_root(self):
        for name in ("script", "style", "textarea", "title"):
            with self.subTest(element=name):
                doc = ("<%s a='x' b= 'y/>" % name
                       + '<html xmlns="%s"><body>'
                         "<p>Real text here.</p></body></html>"
                       % XHTML)
                with self.assertRaises(
                        acquisition.AcquisitionError) as caught:
                    self.extract("page-%s.html" % name, doc)
                self.assertEqual(_token(caught.exception),
                                 "PAGE_EXTRACTION_FAILED")

    def test_stray_equals_form_refuses_the_xhtml_root(self):
        doc = ('<script a="x" = "y/>'
               + '<html xmlns="%s"><body>'
                 "<p>Real text here.</p></body></html>" % XHTML)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract("page-stray.html", doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_plain_self_closed_control_still_refuses(self):
        doc = ("<script/>"
               + '<html xmlns="%s"><body>'
                 "<p>Real text here.</p></body></html>" % XHTML)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract("page-plain.html", doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_closing_spelling_control_still_refuses(self):
        doc = ("<script a='x' b= 'y></script>"
               + '<html xmlns="%s"><body>'
                 "<p>Real text here.</p></body></html>" % XHTML)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract("page-closed.html", doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR6_009RootNamespaceEqualsRun(Base):
    def test_equals_run_with_space_admits(self):
        result = self.extract(
            "a.html",
            '<html xmlns== "%s"><body>'
            "<p>Real text here.</p></body></html>" % XHTML)
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")

    def test_equals_run_with_no_space_admits(self):
        result = self.extract(
            "b.html",
            '<html xmlns=="%s"><body>'
            "<p>Real text here.</p></body></html>" % XHTML)
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")

    def test_equals_run_values_read_as_the_parser_reads_them(self):
        self.assertEqual(
            acquisition._root_tag_xmlns(
                '<html xmlns== "%s">' % XHTML), "=")
        self.assertEqual(
            acquisition._root_tag_xmlns(
                '<html xmlns=="%s">' % XHTML), '="%s"' % XHTML)

    def test_declared_namespace_control_still_refuses(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(
                "c.html",
                '<html xmlns="%s"><body>'
                "<p>Real text here.</p></body></html>" % XHTML)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR6_010AddProductFifthAttemptReturn(Base):
    def test_fifth_attempt_return_judged_on_the_fresh_record(self):
        self.add(name="Example Product")
        entries = journal.fold(self.home)
        product_entry = entries[-1]
        original_version = registry._journal_version
        calls = {"count": 0}

        def hooked(home):
            calls["count"] += 1
            count = calls["count"]
            if count in (2, 4, 6, 8):
                journal.append_entry(
                    self.home, "failure_record",
                    {"operation": "probe",
                     "error_value": "VERSION_PROBE",
                     "subject_identity": "probe-%d" % count,
                     "date": AUDIT_DATE,
                     "rule_fired": "VERSION_PROBE"},
                    audit_date=AUDIT_DATE)
            elif count == 10:
                corrected = dict(product_entry["payload"])
                corrected["domain"] = "corrected.example"
                journal.append_entry(
                    self.home, "correction",
                    {"supersedes_sequence": product_entry["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
            return original_version(home)

        registry._journal_version = hooked
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.add_product(
                    self.home, name="Example Product",
                    canonical_line="A line.", domain="example.com",
                    audit_date=AUDIT_DATE)
            self.assertEqual(_token(caught.exception),
                             "PRODUCT_READD_CHANGED")
        finally:
            registry._journal_version = original_version
        standing = registry.find_product(self.home, "Example Product")
        self.assertEqual(standing["domain"], "corrected.example")

    def test_idempotent_readd_still_returns_the_standing_record(self):
        first = self.add(name="Example Product")
        second = self.add(name="Example Product")
        self.assertEqual(second["product_id"], first["product_id"])
        self.assertEqual(second["domain"], "example.com")
        self.assertEqual(len(registry.list_products(self.home)), 1)

    def test_changed_readd_still_refused(self):
        self.add(name="Example Product")
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(name="Example Product", domain="other.example")
        self.assertEqual(_token(caught.exception),
                         "PRODUCT_READD_CHANGED")


class TestR6_011RegistryFoldIdentityJudgement(Base):
    def _plant_integer_identity(self):
        journal.append_entry(
            self.home, "product_registered",
            {"product_id": 7, "name": "Seven",
             "canonical_line": "A line.", "domain": "seven.example",
             "competitors": [], "aliases": [], "query_set": [],
             "query_set_version": 1, "category": [],
             "registry_version": 1},
            audit_date=AUDIT_DATE)

    def test_mapping_road_integer_identity_refused(self):
        self.add(name="Example Product")
        self._plant_integer_identity()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.list_products(self.home)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_list_road_integer_identity_refused(self):
        original = journal.fold_registry
        journal.fold_registry = lambda home: [
            {"product_id": 7, "name": "Seven"}]
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.list_products(self.home)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")
        finally:
            journal.fold_registry = original

    def test_fallback_road_integer_identity_refused(self):
        self.add(name="Example Product")
        self._plant_integer_identity()
        original = journal.fold_registry
        journal.fold_registry = lambda home: None
        try:
            with self.assertRaises(registry.RegistryError) as caught:
                registry.list_products(self.home)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")
        finally:
            journal.fold_registry = original

    def test_genuine_products_still_list(self):
        self.add(name="Example Product")
        records = registry.list_products(self.home)
        self.assertEqual([item["name"] for item in records],
                         ["Example Product"])


class TestR6_012FrontMatterConstructPositions(Base):
    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_construct_as_its_own_word_in_a_value(self):
        self.assert_page_refuses("title: abc !tag rest")

    def test_anchor_as_its_own_word_on_a_second_key_line(self):
        self.assert_page_refuses("title: abc\nother: x &anchor y")

    def test_alias_as_its_own_word_in_a_value(self):
        self.assert_page_refuses("title: abc *alias rest")

    def test_construct_on_an_indented_continuation_line(self):
        self.assert_page_refuses("title: abc\n  more !tag here")

    def test_construct_inside_a_quoted_key(self):
        self.assert_page_refuses('"!tag title": abc')

    def test_block_scalar_as_the_whole_value(self):
        self.assert_page_refuses("title: |")

    def test_construct_inside_the_json_form(self):
        self.assert_page_refuses('{"title": "abc !tag rest"}')

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("title: abc !tag rest",
                      "title: abc\n  more !tag here",
                      '"!tag title": abc',
                      "title: |",
                      '{"title": "abc !tag rest"}'):
            with self.subTest(block=block):
                with self.assertRaises(
                        probe_import.ProbeImportError) as caught:
                    self.import_front_matter(block)
                self.assertEqual(_token(caught.exception),
                                 "IMPORT_VALIDATION_FAILED")

    def test_plain_block_and_plain_json_still_pass(self):
        self.assertEqual(
            self.page_front_matter("title: abc"), "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "abc"}'), "body text")


class TestR6_013FrontMatterBracketJudgement(Base):
    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_unbalanced_bracket_in_the_key_part(self):
        self.assert_page_refuses("ti[tle: abc")

    def test_unbalanced_brace_in_the_key_part(self):
        self.assert_page_refuses("ti{tle: abc")

    def test_unbalanced_bracket_as_a_whole_value(self):
        self.assert_page_refuses("title: [abc")

    def test_unbalanced_bracket_on_a_continuation_line(self):
        self.assert_page_refuses("title: abc\n  more [abc here")

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("ti[tle: abc", "title: [abc",
                      "title: abc\n  more [abc here"):
            with self.subTest(block=block):
                with self.assertRaises(
                        probe_import.ProbeImportError) as caught:
                    self.import_front_matter(block)
                self.assertEqual(_token(caught.exception),
                                 "IMPORT_VALIDATION_FAILED")

    def test_balanced_brackets_still_pass(self):
        self.assertEqual(
            self.page_front_matter("title: [abc]"), "body text")


class TestR6_014FrontMatterKeyDiscipline(Base):
    def test_duplicate_key_refused_on_the_page_side(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter("title: abc\ntitle: def")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter("title: abc\ntitle: def")
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def test_key_count_limit_refused_on_the_page_side(self):
        block = "\n".join("key%d: v" % index for index in range(101))
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_one_hundred_distinct_keys_still_pass(self):
        block = "\n".join("key%d: v" % index for index in range(100))
        self.assertEqual(self.page_front_matter(block), "body text")


class TestR6_015ContentProbeVocabularyChildren(Base):
    SVG_CHILDREN = (
        "circle", "path", "defs", "ellipse", "rect", "polygon",
        "polyline", "g", "text", "use", "filter", "animate",
        "clipPath", "foreignObject", "image", "line",
        "linearGradient", "marker", "mask", "metadata", "mpath",
        "pattern", "radialGradient", "set", "stop", "switch",
        "symbol", "textPath", "tspan", "view", "desc",
        "animateMotion", "animateTransform", "feGaussianBlur",
        "feBlend",
    )
    MATHML_CHILDREN = (
        "mi", "mo", "mn", "ms", "mtext", "mrow", "mfrac",
        "msqrt", "mroot", "msub", "msup", "msubsup", "munder",
        "mover", "munderover", "mtable", "mtr", "mtd",
        "annotation-xml", "annotation", "semantics", "menclose",
        "merror", "mphantom", "mpadded", "mspace", "mstyle",
        "maction", "mmultiscripts", "mprescripts", "none",
    )

    def test_svg_child_led_documents_detect_as_html(self):
        for tag in self.SVG_CHILDREN:
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    "<%s><p>hello content here</p>" % tag,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_mathml_child_led_documents_detect_as_html(self):
        for tag in self.MATHML_CHILDREN:
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    "<%s><p>hello content here</p>" % tag,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_plain_prose_still_decides_no_format(self):
        self.assertIsNone(acquisition._content_format(
            "A plain sentence with no markup at all."))


if __name__ == "__main__":
    unittest.main()
