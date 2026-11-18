"""Registry and acquisition.

Test first pins for register to and. Each test reproduces the
defect named under the settled rule, then stands as the pin for
its cure."""

import os
import tempfile
import unittest

from citeline import acquisition, probe_import

AUDIT_DATE = "2026-11-14"


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

    def write_page(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8", newline="") as handle:
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

    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def assert_page_limit(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def assert_import_refuses(self, block):
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")


class TestR8_003ConstructCompletedForms(Base):
    def test_caret_angle_spelling_in_a_value(self):
        self.assert_page_refuses("title: <^tag> rest")

    def test_caret_angle_spelling_as_a_key(self):
        self.assert_page_refuses("<^tag>: abc")

    def test_caret_angle_spelling_inside_a_json_value(self):
        self.assert_page_refuses('{"title": "<^tag> rest"}')

    def test_caret_angle_spelling_red_form(self):
        self.assert_page_refuses("title: <^foo>")

    def test_construct_directly_after_a_comma(self):
        self.assert_page_refuses("title: a,!tag x")

    def test_anchor_directly_after_a_semicolon(self):
        self.assert_page_refuses("title: a;&anchor x")

    def test_construct_directly_after_a_colon(self):
        self.assert_page_refuses("title: a:!tag x")

    def test_anchor_directly_after_a_flow_mapping_colon(self):
        self.assert_page_refuses("title: {k:&b}")

    def test_construct_directly_after_a_quote(self):
        self.assert_page_refuses('title: a"!tag x')

    def test_construct_directly_after_an_opening_parenthesis(self):
        self.assert_page_refuses("title: a(!tag x")

    def test_comma_form_inside_a_json_string_value(self):
        self.assert_page_refuses('{"title": "a,!tag x"}')

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("title: <^tag> rest", "<^tag>: abc",
                      '{"title": "<^tag> rest"}',
                      "title: a,!tag x", "title: a;&anchor x",
                      "title: a:!tag x", "title: {k:&b}",
                      'title: a"!tag x', "title: a(!tag x",
                      '{"title": "a,!tag x"}'):
            with self.subTest(block=block):
                self.assert_import_refuses(block)

    def test_plain_block_and_plain_json_still_pass(self):
        self.assertEqual(
            self.page_front_matter("title: abc"), "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "abc"}'), "body text")

    def test_caret_form_stores_nothing_end_to_end(self):
        doc = "---\ntitle: <^tag> rest\n---\n# Heading\n\nbody\n"
        path = self.write_page("page.md", doc)
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition.extract_page(
                self.home, product_id="p-example", page_path=path,
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR8_004DuplicateOnJudgedKeyInterior(Base):
    def test_line_form_zero_width_space_inside_the_second_key(self):
        self.assert_page_refuses("title: abc\nti\u200btle: def")

    def test_line_form_combining_grapheme_joiner_inside_key(self):
        self.assert_page_refuses("title: abc\nti\u034ftle: def")

    def test_line_form_byte_order_mark_inside_the_second_key(self):
        self.assert_page_refuses("title: abc\nti\ufefftle: def")

    def test_json_form_zero_width_space_at_the_key_edge(self):
        self.assert_page_refuses(
            '{"title": "one", "\u200btitle": "two"}')

    def test_json_form_zero_width_space_inside_the_key(self):
        self.assert_page_refuses(
            '{"title": "one", "ti\u200btle": "two"}')

    def test_json_form_byte_order_mark_inside_the_key(self):
        self.assert_page_refuses(
            '{"title": "one", "ti\ufefftle": "two"}')

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("title: abc\nti\u200btle: def",
                      "title: abc\nti\u034ftle: def",
                      '{"title": "one", "\u200btitle": "two"}',
                      '{"title": "one", "ti\u200btle": "two"}',
                      '{"title": "one", "ti\ufefftle": "two"}'):
            with self.subTest(block=block):
                self.assert_import_refuses(block)

    def test_plain_duplicate_control_refuses_on_both(self):
        self.assert_page_refuses("title: abc\ntitle: def")
        self.assert_import_refuses("title: abc\ntitle: def")

    def test_distinct_keys_still_pass_in_both_forms(self):
        self.assertEqual(
            self.page_front_matter("title: abc\nother: def"),
            "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "one", "other": "two"}'),
            "body text")


class TestR8_005FenceInteriorHeadMaterial(Base):
    def test_opening_fence_dashes_separated_by_zero_width_spaces(self):
        text = "-\u200b-\u200b-\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_opening_fence_dashes_separated_by_byte_order_mark(self):
        text = "-\ufeff--\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_closing_fence_dashes_separated_by_zero_width_spaces(self):
        text = "---\ntitle: abc\n-\u200b-\u200b-\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_closing_fence_dashes_separated_by_byte_order_mark(self):
        text = "---\ntitle: abc\n-\ufeff--\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")

    def test_import_side_reads_the_same_interior_fences(self):
        for text in (
                "-\u200b-\u200b-\ntitle: abc\n---\nbody text\n",
                "---\ntitle: abc\n-\u200b-\u200b-\nbody text\n"):
            with self.subTest(text=text):
                body, had = probe_import.extract_front_matter(text)
                self.assertTrue(had)
                self.assertEqual(body, "body text")

    def test_plain_fence_control_reads_as_a_block(self):
        text = "---\ntitle: abc\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")


class TestR8_006JsonNumberWrittenForm(Base):
    def test_number_written_with_long_decimal_tail(self):
        block = '{"title": 0.' + "0" * 5000 + "1}"
        self.assert_page_limit(block)

    def test_number_written_with_long_exponent(self):
        block = '{"title": 1e' + "9" * 5000 + "}"
        self.assert_page_limit(block)

    def test_import_side_refuses_the_same_numbers(self):
        for block in ('{"title": 0.' + "0" * 5000 + "1}",
                      '{"title": 1e' + "9" * 5000 + "}"):
            with self.subTest(block=block[:30]):
                with self.assertRaises(
                        probe_import.ProbeImportError) as caught:
                    self.import_front_matter(block)
                self.assertEqual(_token(caught.exception),
                                 "LIMIT_EXCEEDED")

    def test_short_number_still_passes(self):
        self.assertEqual(
            self.page_front_matter('{"title": 123}'), "body text")

    def test_number_written_below_the_limit_still_passes(self):
        block = '{"title": 1' + "0" * 100 + "}"
        self.assertEqual(self.page_front_matter(block), "body text")


class TestR8_007BlockSizeOnFileForm(Base):
    def _block_lines(self):
        return ["# " + "x" * 160] * 100

    def test_crlf_block_past_the_limit_refuses_on_the_page_side(self):
        text = "---\r\n" + "\r\n".join(self._block_lines()) \
            + "\r\n---\r\nbody text\r\n"
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.front_matter_text(text)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_crlf_block_past_the_limit_refuses_on_import_side(self):
        text = "---\r\n" + "\r\n".join(self._block_lines()) \
            + "\r\n---\r\nbody text\r\n"
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            probe_import.extract_front_matter(text)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_newline_control_of_the_same_block_passes_both(self):
        text = "---\n" + "\n".join(self._block_lines()) \
            + "\n---\nbody text\n"
        self.assertEqual(self.front_matter_text(text), "body text")
        body, had = probe_import.extract_front_matter(text)
        self.assertTrue(had)
        self.assertEqual(body, "body text")

    def test_small_crlf_block_still_reads_as_a_block(self):
        text = "---\r\ntitle: abc\r\n---\r\nbody text\r\n"
        self.assertEqual(self.front_matter_text(text), "body text")


class TestR8_028ContainerStringCharacterMeasure(Base):
    def test_string_of_4094_inside_a_list_passes(self):
        block = '{"title": ["' + "x" * 4094 + '"]}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_string_of_4095_inside_a_list_passes(self):
        block = '{"title": ["' + "x" * 4095 + '"]}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_string_of_4096_inside_a_list_passes(self):
        block = '{"title": ["' + "x" * 4096 + '"]}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_string_of_4096_inside_a_nested_list_passes(self):
        block = '{"title": [["' + "x" * 4096 + '"]]}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_string_of_4096_inside_a_dict_value_refuses(self):
        # Corrected at the repair under the settled rule of the
        # settled disposition: the pin as first written
        # stated the standing before the cure at. On the
        # cured standing a key standing inside a container
        # stands measured by its length in characters
        # beside the measure of its value, so the key k at
        # 1 character beside the string of 4096 sums to
        # 4097 and stands refused where their sum passes
        # the limit, and the string of 4095 beside the same
        # key sums to the limit and passes.
        block = '{"title": {"k": "' + "x" * 4096 + '"}}'
        self.assert_page_limit(block)
        block = '{"title": {"k": "' + "x" * 4095 + '"}}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_string_of_5000_inside_a_list_refuses_at_both(self):
        block = '{"title": ["' + "x" * 5000 + '"]}'
        self.assert_page_limit(block)
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def test_whole_value_string_at_the_limit_control_passes(self):
        block = '{"title": "' + "x" * 4096 + '"}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_import_side_accepts_the_at_limit_list_strings(self):
        for size in (4094, 4095, 4096):
            with self.subTest(size=size):
                block = '{"title": ["' + "x" * size + '"]}'
                body, had = self.import_front_matter(block)
                self.assertTrue(had)

    def test_number_inside_a_container_on_its_written_form(self):
        block = '{"title": [0.' + "0" * 5000 + "1]}"
        self.assert_page_limit(block)


if __name__ == "__main__":
    unittest.main()
