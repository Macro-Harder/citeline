"""Step 17 fix seat F2 tests, registry and acquisition.

Test first pins for register entries S17-R1-008 to
S17-R1-013, S17-R1-015 to S17-R1-019, and S17-R1-088.
Each test reproduces the defect named at its register
entry against the governing brief or plan text cited
there, then stands as the pin for its cure.
"""

import multiprocessing
import os
import tempfile
import time
import unittest

from citeline import acquisition, registry

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


class TestS17R1008NfcIdentity(RegistryBase):
    def test_decomposed_name_is_readd_of_composed_name(self):
        first = self.add(name="Café")
        second = self.add(name="Café")
        self.assertEqual(second["product_id"], first["product_id"])
        self.assertEqual(len(registry.list_products(self.home)), 1)

    def test_decomposed_name_with_change_is_readd_changed(self):
        self.add(name="Café")
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(name="Café", domain="other.com")
        self.assertEqual(_token(caught.exception),
                         "PRODUCT_READD_CHANGED")
        self.assertEqual(len(registry.list_products(self.home)), 1)


class TestS17R1009EmptySlug(RegistryBase):
    def test_names_with_no_slug_content_are_refused(self):
        for index, name in enumerate(
                ("   ", "!!!", "..", "製品")):
            home = self.fresh_home("h%d" % index)
            with self.assertRaises(registry.RegistryError) as caught:
                self.add(home=home, name=name)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")
            self.assertEqual(registry.list_products(home), [])


class TestS17R1010Surrogates(RegistryBase):
    def test_surrogate_in_name_fails_validation(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(name="Bad\ud800Name")
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")
        self.assertEqual(registry.list_products(self.home), [])

    def test_surrogate_in_canonical_line_fails_validation(self):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(canonical_line="bad\ud800line")
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_surrogate_set_canonical_line_fails_validation(self):
        self.add()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_canonical_line(
                self.home, "Example Product", "bad\ud800line",
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")


class TestS17R1011ListForms(RegistryBase):
    def test_non_list_query_set_fails_validation(self):
        self.add()
        with self.assertRaises(registry.RegistryError) as caught:
            registry.set_query_set(self.home, "Example Product", 123,
                                   audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_string_query_set_is_not_split_into_characters(self):
        self.add()
        with self.assertRaises(registry.RegistryError):
            registry.set_query_set(self.home, "Example Product", "abc",
                                   audit_date=AUDIT_DATE)
        record = registry.get_product(self.home, "Example Product")
        self.assertEqual(record["query_set"], [])

    def test_non_list_category_and_string_category_fail(self):
        self.add()
        for bad in (123, "abc"):
            with self.assertRaises(registry.RegistryError):
                registry.set_category(self.home, "Example Product",
                                      bad, audit_date=AUDIT_DATE)

    def test_non_list_aliases_and_competitors_fail(self):
        with self.assertRaises(registry.RegistryError):
            self.add(aliases=123)
        with self.assertRaises(registry.RegistryError):
            self.add(name="Other Product", competitors=123)
        self.add()
        with self.assertRaises(registry.RegistryError):
            registry.set_aliases(self.home, "Example Product", 123,
                                 audit_date=AUDIT_DATE)
        with self.assertRaises(registry.RegistryError):
            registry.set_competitors(self.home, "Example Product",
                                     "abc", audit_date=AUDIT_DATE)


class TestS17R1012DomainForm(RegistryBase):
    def test_non_host_domains_are_refused(self):
        bad_domains = (
            "user@example.com", "exa_mple.com", "-bad.com",
            "bad-.com", "_bad.com", "-.com", "%65xample.com",
            "exam\u200bple.com")
        for index, domain in enumerate(bad_domains):
            home = self.fresh_home("d%d" % index)
            with self.assertRaises(registry.RegistryError) as caught:
                self.add(home=home, name="Product %d" % index,
                         domain=domain)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED", domain)
            self.assertEqual(registry.list_products(home), [])

    def test_unicode_domain_forms_still_normalise(self):
        record = self.add(name="Munich Product",
                          domain="mu\u0308nchen.de")
        self.assertEqual(record["domain"], "xn--mnchen-3ya.de")
        other = self.add(name="Dot Product",
                         domain="example\u3002com")
        self.assertEqual(other["domain"], "example.com")


class TestS17R1013PathPrefix(RegistryBase):
    def test_prefix_normalisation_cases(self):
        cases = (
            ("/a/../b", "/b"),
            ("/../secret", "/secret"),
            ("/%2e%2e/evil", "/evil"),
            ("/%41bc", "/Abc"),
            ("/a/./b", "/a/b"),
            ("/a/%2f", "/a/%2F"),
            ("/docs/", "/docs"),
            ("/", "/"),
        )
        for index, (given, expected) in enumerate(cases):
            record = self.add(name="Prefix Product %d" % index,
                              path_prefix=given)
            self.assertEqual(record["path_prefix"], expected, given)

    def test_prefix_with_control_character_is_refused(self):
        for bad in ("/a\nb", "/a\x01b"):
            with self.assertRaises(registry.RegistryError) as caught:
                self.add(name="Control Product", path_prefix=bad)
            self.assertEqual(_token(caught.exception),
                             "VALIDATION_FAILED")


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


class TestS17R1015ScriptStyle(AcquisitionBase):
    def test_comment_shielded_unclosed_script_fails(self):
        path = self.write_page(
            "s2.html",
            "<html><body><!-- </script> --><p>Before text.</p>"
            "<script>var x=1;<p>After swallowed text here.</p>"
            "</body></html>")
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(path)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_comment_shielded_unclosed_style_fails(self):
        path = self.write_page(
            "s3.html",
            "<html><body><!-- </style> --><p>Before text.</p>"
            "<style>.x { color: red; }<p>After text here.</p>"
            "</body></html>")
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(path)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_self_closed_script_element_extracts(self):
        path = self.write_page(
            "s8.html",
            "<html><body><script src='x.js'/><p>Real page text "
            "here.</p></body></html>")
        result = self.extract(path)
        self.assertIn("Real page text here.",
                      result["extracted"]["running_text"])


class TestS17R1016BracketScan(AcquisitionBase):
    def test_unmatched_brackets_extract_within_bound(self):
        path = self.write_page(
            "brackets.md", "[" * 10000 + "\n\nBody text here.\n")
        start = time.monotonic()
        result = self.extract(path)
        elapsed = time.monotonic() - start
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")
        self.assertLess(elapsed, 2.0)

    def test_unmatched_link_prefixes_extract_within_bound(self):
        path = self.write_page(
            "links.md", "[a](x" * 6000 + "\n\nBody text here.\n")
        start = time.monotonic()
        result = self.extract(path)
        elapsed = time.monotonic() - start
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")
        self.assertLess(elapsed, 2.0)


class TestS17R1017Containers(AcquisitionBase):
    def assert_container_fails(self, name, content):
        path = self.write_page(name, content)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(path)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_xhtml_namespace_past_4096_fails(self):
        self.assert_container_fails(
            "x2.html",
            "<html " + " " * 5000 +
            'xmlns="http://www.w3.org/1999/xhtml">'
            "<body><p>Body text here.</p></body></html>")

    def test_xhtml_doctype_past_4096_fails(self):
        self.assert_container_fails(
            "x1.html",
            " " * 5000 +
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 '
            'Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/'
            'xhtml1-strict.dtd">'
            "<html><body><p>Body text here.</p></body></html>")

    def test_mhtml_headers_past_4096_fail(self):
        padding = "".join("X-Pad: %s\n" % ("p" * 40) for _ in range(90))
        self.assert_container_fails(
            "x3.html",
            padding +
            "MIME-Version: 1.0\n"
            "Content-Type: multipart/related; boundary=\"b\"\n"
            "\n--b\nContent-Type: text/html\n\n"
            "<html><body><p>Body text here.</p></body></html>\n--b--\n")

    def test_warc_signature_after_blank_line_fails(self):
        self.assert_container_fails(
            "w1.html",
            "\nWARC/1.0\r\nWARC-Type: response\r\n\r\n"
            "<html><body><p>Body text here.</p></body></html>")


class TestS17R1018NulPath(AcquisitionBase):
    def test_nul_in_page_path_is_supplied_path_unsafe(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition.extract_page(
                self.home, product_id="p-example",
                page_path="bad\x00path.html", audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "SUPPLIED_PATH_UNSAFE")


class TestS17R1019LeadingHtml(AcquisitionBase):
    def test_leading_html_element_forms_detect_as_html(self):
        cases = (
            ("section",
             "<section><h1>Heading Text</h1><p>Body paragraph "
             "text here.</p></section>"),
            ("article",
             "<article><h1>Head Text</h1><p>Body paragraph text "
             "here.</p></article>"),
            ("blockquote",
             "<blockquote><p>Quoted body text here.</p>"
             "</blockquote>"),
            ("pre", "<pre>Preformatted body text here.</pre>"),
            ("main", "<main><p>Main body text here.</p></main>"),
            ("em", "<em>Emphasis</em> and plain text follows here."),
        )
        for label, content in cases:
            path = self.write_page("page-%s.txt" % label, content)
            result = self.extract(path)
            self.assertEqual(result["snapshot"]["detected_format"],
                             "html", label)
            self.assertNotIn("<", result["extracted"]["running_text"],
                             label)

    def test_section_page_heading_stands_as_heading(self):
        path = self.write_page(
            "section.txt",
            "<section><h1>Heading Text</h1><p>Body paragraph "
            "text here.</p></section>")
        result = self.extract(path)
        texts = [h["text"] for h in result["extracted"]["headings"]]
        self.assertIn("Heading Text", texts)


def _concurrent_setter(home, name, kind, barrier, queue):
    try:
        barrier.wait(timeout=30)
        if kind == "aliases":
            registry.set_aliases(home, name, ["round-alias"],
                                 audit_date=AUDIT_DATE)
        else:
            registry.set_competitors(
                home, name,
                [{"name": "Round Rival", "domain": "rival.com",
                  "aliases": []}],
                audit_date=AUDIT_DATE)
        queue.put((kind, "ok"))
    except Exception as exc:
        queue.put((kind, "error: %r" % (exc,)))


class TestS17R1088ConcurrentRegistry(unittest.TestCase):
    def test_concurrent_setters_both_stand(self):
        ctx = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            os.makedirs(home)
            for round_index in range(8):
                name = "Round Product %d" % round_index
                created = registry.add_product(
                    home, name=name, canonical_line="A line.",
                    domain="example.com", audit_date=AUDIT_DATE)
                barrier = ctx.Barrier(2)
                queue = ctx.Queue()
                workers = [
                    ctx.Process(
                        target=_concurrent_setter,
                        args=(home, name, kind, barrier, queue))
                    for kind in ("aliases", "competitors")
                ]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(timeout=60)
                results = [queue.get(timeout=10) for _ in workers]
                self.assertEqual(
                    sorted(results),
                    [("aliases", "ok"), ("competitors", "ok")],
                    "round %d" % round_index)
                record = registry.get_product(home, name)
                self.assertEqual(record["aliases"], ["round-alias"],
                                 "round %d" % round_index)
                self.assertEqual(
                    [c["name"] for c in record["competitors"]],
                    ["Round Rival"], "round %d" % round_index)
                self.assertEqual(
                    record["registry_version"],
                    created["registry_version"] + 2,
                    "round %d" % round_index)


if __name__ == "__main__":
    unittest.main()
