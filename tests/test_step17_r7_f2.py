"""Step 17 round 7 fix seat F2 tests, registry and acquisition.

Test first pins for register entries S17-R7-008 to
S17-R7-018. Each test reproduces the defect named at
its register entry, then stands as the pin for its
cure.
"""

import os
import tempfile
import unittest

from citeline import acquisition, probe_import, registry

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

    def front_matter_text(self, text):
        notes = []
        return acquisition._front_matter(text, "markdown", notes)

    def name_round(self, label, product="Example Product"):
        return registry.name_round(
            self.home, product=product, round_label=label,
            importer_declaration="all_captured",
            supplier_relation="independent",
            audit_date=AUDIT_DATE)


class TestR7_008BracketAtLineStart(Base):
    def assert_refused(self, name, doc):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract(name, doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_script_close_bracket_at_line_start_refuses(self):
        doc = ("<script>var x = 1;</script\n"
               "><html xmlns=\"%s\"><body>"
               "<p>Real text here.</p></body></html>" % XHTML)
        self.assert_refused("a.html", doc)

    def test_style_close_bracket_at_line_start_refuses(self):
        doc = ("<style>p { color: red; }</style\n"
               "><html xmlns=\"%s\"><body>"
               "<p>Real text here.</p></body></html>" % XHTML)
        self.assert_refused("b.html", doc)

    def test_root_tag_bracket_at_line_start_refuses(self):
        doc = ("<html xmlns=\"%s\"\n"
               "><body><p>Real text here.</p></body></html>"
               % XHTML)
        self.assert_refused("c.html", doc)

    def test_genuine_blockquote_root_spelling_still_stores(self):
        doc = ("> <html xmlns=\"%s\"><body>quoted</body></html>\n"
               "<html><body><p>Real text here.</p></body></html>"
               % XHTML)
        result = self.extract("d.html", doc)
        self.assertEqual(
            result["snapshot"]["extraction_outcome"], "ok")


class TestR7_009ConstructCompletedForms(Base):
    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_angle_spelling_opening_on_a_digit_in_a_value(self):
        self.assert_page_refuses("title: <1tag> rest")

    def test_angle_spelling_opening_on_a_hyphen_in_a_value(self):
        self.assert_page_refuses("title: <-tag> rest")

    def test_angle_spelling_opening_on_an_underscore_in_a_value(self):
        self.assert_page_refuses("title: <_tag> rest")

    def test_angle_spelling_opening_on_a_digit_as_a_key(self):
        self.assert_page_refuses("<1tag>: abc")

    def test_angle_spelling_on_a_continuation_line(self):
        self.assert_page_refuses("title: abc\n  <1tag> here")

    def test_angle_spelling_inside_a_json_string_value(self):
        self.assert_page_refuses('{"title": "<1tag> rest"}')

    def test_block_scalar_reversed_order_literal(self):
        self.assert_page_refuses("title: |2+")

    def test_block_scalar_reversed_order_folded(self):
        self.assert_page_refuses("title: >2-")

    def test_block_scalar_reversed_order_inside_json(self):
        self.assert_page_refuses('{"title": "|2+"}')

    def test_construct_directly_after_a_flow_square_bracket(self):
        self.assert_page_refuses("title: [!tag x]")

    def test_anchor_directly_after_a_flow_brace(self):
        self.assert_page_refuses("title: {&anchor x}")

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("title: <1tag> rest", "title: <-tag> rest",
                      "title: <_tag> rest", "<1tag>: abc",
                      "title: |2+", "title: >2-",
                      "title: [!tag x]", "title: {&anchor x}",
                      '{"title": "<1tag> rest"}'):
            with self.subTest(block=block):
                with self.assertRaises(
                        probe_import.ProbeImportError) as caught:
                    self.import_front_matter(block)
                self.assertEqual(_token(caught.exception),
                                 "IMPORT_VALIDATION_FAILED")

    def test_stated_indicator_order_control_refuses_on_both(self):
        self.assert_page_refuses("title: |+2")

    def test_plain_block_and_plain_json_still_pass(self):
        self.assertEqual(
            self.page_front_matter("title: abc"), "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "abc"}'), "body text")


class TestR7_010DuplicateOnJudgedKey(Base):
    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_zero_width_space_before_the_second_key(self):
        self.assert_page_refuses("title: abc\n\u200btitle: def")

    def test_zero_width_space_after_the_second_key_name(self):
        self.assert_page_refuses("title: abc\ntitle\u200b: def")

    def test_byte_order_mark_before_the_second_key(self):
        self.assert_page_refuses("title: abc\n\ufefftitle: def")

    def test_variation_selector_before_the_second_key(self):
        self.assert_page_refuses("title: abc\n\ufe0ftitle: def")

    def test_combining_grapheme_joiner_before_the_second_key(self):
        self.assert_page_refuses("title: abc\n\u034ftitle: def")

    def test_plain_duplicate_control_refuses_on_both(self):
        self.assert_page_refuses("title: abc\ntitle: def")
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter("title: abc\ntitle: def")
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")


class TestR7_011HeadStripDefaultIgnorable(Base):
    def test_variation_selector_before_a_construct_at_value_head(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter("title: \ufe0f!tag rest")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_combining_grapheme_joiner_before_a_construct(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter("title: \u034f!tag rest")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_byte_order_mark_head_control_refuses_as_before(self):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter("title: \ufeff!tag rest")
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR7_012EmptyKeyJudgement(Base):
    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_line_holding_only_a_colon_and_a_value(self):
        self.assert_page_refuses(": abc")

    def test_line_holding_a_colon_and_an_empty_value(self):
        self.assert_page_refuses("title: abc\n: ")

    def test_import_side_refuses_the_same_line(self):
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter(": abc")
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")


class TestR7_013JsonValueAndDepthLimits(Base):
    def assert_page_limit(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_json_string_value_past_the_length_limit(self):
        self.assert_page_limit('{"title": "' + "x" * 5000 + '"}')

    def test_json_value_nested_past_the_depth_limit(self):
        block = '{"title": ' + "[" * 101 + "]" * 101 + "}"
        self.assert_page_limit(block)

    def test_json_string_value_at_the_length_limit_passes(self):
        block = '{"title": "' + "x" * 4096 + '"}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_json_value_nested_fifty_deep_passes(self):
        block = '{"title": ' + "[" * 50 + "]" * 50 + "}"
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_json_escaped_newline_value_on_character_measure(self):
        block = '{"title": "' + "\\n" * 3000 + '"}'
        self.assertEqual(self.page_front_matter(block), "body text")


class TestR7_014FenceOnCompletedHeadPredicate(Base):
    def test_opening_fence_with_a_trailing_zero_width_space(self):
        text = "---\u200b\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_opening_fence_with_a_trailing_byte_order_mark(self):
        text = "---\ufeff\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_opening_fence_with_a_trailing_variation_selector(self):
        text = "---\ufe0f\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_zero_width_space_before_the_opening_fence(self):
        text = "\u200b---\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_variation_selector_before_the_opening_fence(self):
        text = "\ufe0f---\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_closing_fence_with_a_trailing_zero_width_space(self):
        text = "---\ntitle: abc\n---\u200b\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_plain_fence_control_reads_as_a_block(self):
        text = "---\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")


class TestR7_015ContentProbeElementCompletion(Base):
    NAMES = (
        "font-face", "font-face-format", "font-face-name",
        "font-face-src", "font-face-uri",
        "maligngroup", "malignmark",
    )

    def test_named_elements_detect_as_html(self):
        for tag in self.NAMES:
            with self.subTest(tag=tag):
                detected = acquisition.detect_format(
                    "<%s><p>hello content here</p>" % tag,
                    filename="page.txt")
                self.assertEqual(detected["detected_format"], "html")

    def test_spelling_font_stands_outside_the_cure(self):
        self.assertIsNone(acquisition._content_format(
            "<font><p>hello content here</p>"))


class TestR7_016RoundLabelCharacterJudgement(Base):
    def setUp(self):
        super().setUp()
        self.add()

    def assert_label_refused(self, label):
        with self.assertRaises(registry.RegistryError) as caught:
            self.name_round(label)
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_label_holding_a_newline(self):
        self.assert_label_refused("round\none")

    def test_label_holding_a_nul_character(self):
        self.assert_label_refused("round\x00one")

    def test_label_holding_a_tab(self):
        self.assert_label_refused("round\tone")

    def test_label_holding_a_del_character(self):
        self.assert_label_refused("round\x7fone")

    def test_label_holding_a_lone_surrogate(self):
        self.assert_label_refused("round\ud800one")

    def test_plain_label_control_still_stores(self):
        record = self.name_round("round-one")
        self.assertEqual(record["round_label"], "round-one")


class TestR7_017RoundLabelNormalisation(Base):
    def setUp(self):
        super().setUp()
        self.add()

    def test_decomposed_spelling_of_a_standing_label_refuses(self):
        composed = "caf\u00e9 round"
        decomposed = "cafe\u0301 round"
        self.name_round(composed)
        with self.assertRaises(registry.RegistryError) as caught:
            self.name_round(decomposed)
        self.assertEqual(_token(caught.exception),
                         "ROUND_LABEL_EXISTS")

    def test_label_stored_in_its_composed_form(self):
        record = self.name_round("cafe\u0301 round")
        self.assertEqual(record["round_label"], "caf\u00e9 round")
        self.assertEqual(
            record["round_id"],
            registry.round_id_for(
                record["product_id"], "caf\u00e9 round"))

    def test_exact_duplicate_control_refuses_as_before(self):
        self.name_round("round-one")
        with self.assertRaises(registry.RegistryError) as caught:
            self.name_round("round-one")
        self.assertEqual(_token(caught.exception),
                         "ROUND_LABEL_EXISTS")


class TestR7_018AliasFormatCategory(Base):
    def assert_alias_refused(self, alias):
        with self.assertRaises(registry.RegistryError) as caught:
            self.add(name="Alias Product", aliases=[alias])
        self.assertEqual(_token(caught.exception),
                         "VALIDATION_FAILED")

    def test_alias_carrying_a_soft_hyphen(self):
        self.assert_alias_refused("abc\u00ad")

    def test_alias_carrying_an_arabic_letter_mark(self):
        self.assert_alias_refused("abc\u061c")

    def test_alias_carrying_an_invisible_plus(self):
        self.assert_alias_refused("abc\u2064")

    def test_listed_zero_width_controls_refuse_as_before(self):
        self.assert_alias_refused("abc\u2060")
        self.assert_alias_refused("abc\u200b")

    def test_plain_alias_control_still_stores(self):
        record = self.add(name="Alias Product", aliases=["abc"])
        self.assertEqual(record["aliases"], ["abc"])


if __name__ == "__main__":
    unittest.main()
