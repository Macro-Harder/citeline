"""Registry and acquisition.

Test first pins for register, and. Each test reproduces the
defect named at its register entry, then stands as the pin for
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

    def page_front_matter(self, block):
        text = "---\n" + block + "\n---\nbody text\n"
        notes = []
        return acquisition._front_matter(text, "markdown", notes)

    def import_front_matter(self, block):
        text = "---\n" + block + "\n---\nbody text\n"
        return probe_import.extract_front_matter(text)

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

    def assert_import_limit(self, block):
        with self.assertRaises(probe_import.ProbeImportError) as caught:
            self.import_front_matter(block)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")

    def extract_doc(self, doc):
        path = self.write_page("page.md", doc)
        return acquisition.extract_page(
            self.home, product_id="p-example", page_path=path,
            audit_date=AUDIT_DATE)


class TestR9_002ClosingBracketAndHashAngle(Base):
    def test_line_value_after_closing_square_bracket(self):
        self.assert_page_refuses("title: [x]&a")

    def test_line_value_after_closing_curly_brace(self):
        self.assert_page_refuses("title: {x}&a")

    def test_line_value_after_closing_parenthesis(self):
        self.assert_page_refuses("title: (x)&a")

    def test_line_hash_angle_spelling_in_a_value(self):
        self.assert_page_refuses("title: <#tag>")

    def test_line_hash_angle_spelling_as_a_key(self):
        self.assert_page_refuses("<#tag>: abc")

    def test_json_value_closing_bracket_forms(self):
        for block in ('{"title": "x]&a"}', '{"title": "x}&a"}',
                      '{"title": "x)&a"}'):
            with self.subTest(block=block):
                self.assert_page_refuses(block)

    def test_json_value_nested_closing_bracket_forms(self):
        for block in ('{"title": "[[x]&a]"}',
                      '{"title": "{k:[y]&a}"}'):
            with self.subTest(block=block):
                self.assert_page_refuses(block)

    def test_json_hash_angle_spelling_in_a_value(self):
        self.assert_page_refuses('{"title": "<#tag>"}')

    def test_json_hash_angle_spelling_as_a_key(self):
        self.assert_page_refuses('{"<#tag>": "v"}')

    def test_json_closing_parenthesis_form_as_a_key(self):
        self.assert_page_refuses('{"title": "v", "(x)&a": "w"}')

    def test_import_side_refuses_the_same_blocks(self):
        for block in ("title: [x]&a", "title: {x}&a",
                      "title: (x)&a", "title: <#tag>",
                      "<#tag>: abc", '{"title": "x]&a"}',
                      '{"title": "<#tag>"}', '{"<#tag>": "v"}',
                      '{"title": "v", "(x)&a": "w"}'):
            with self.subTest(block=block):
                self.assert_import_refuses(block)

    def test_plain_block_and_plain_json_still_pass(self):
        self.assertEqual(
            self.page_front_matter("title: abc"), "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "abc"}'), "body text")

    def test_hash_angle_json_form_stores_nothing_end_to_end(self):
        doc = '---\n{"title": "<#tag>"}\n---\n# Heading\n\nbody\n'
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract_doc(doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def test_closing_parenthesis_line_form_stores_nothing(self):
        doc = "---\ntitle: (x)&a\n---\n# Heading\n\nbody\n"
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract_doc(doc)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR9_003ContainerKeyMeasure(Base):
    def test_measure_counts_one_character_key_beside_its_value(self):
        measure = acquisition._fm_container_value_measure(
            {"m": "x" * 4096})
        self.assertEqual(measure, 4097)

    def test_measure_counts_a_key_beside_a_short_value(self):
        measure = acquisition._fm_container_value_measure(
            {"k" * 4090: "x" * 10})
        self.assertEqual(measure, 4100)

    def test_one_character_key_beside_a_value_at_the_limit(self):
        block = '{"v": {"m": "' + "x" * 4096 + '"}}'
        self.assert_page_limit(block)

    def test_key_past_the_limit_inside_a_nested_mapping(self):
        block = '{"v": {"' + "k" * 5000 + '": "s"}}'
        self.assert_page_limit(block)

    def test_key_past_the_limit_inside_a_mapping_in_a_list(self):
        block = '{"v": [{"' + "k" * 5000 + '": "s"}]}'
        self.assert_page_limit(block)

    def test_key_and_value_together_past_the_limit(self):
        block = '{"v": {"' + "k" * 4090 + '": "' + "x" * 10 + '"}}'
        self.assert_page_limit(block)

    def test_key_of_4000_inside_a_container_still_passes(self):
        block = '{"v": {"' + "k" * 4000 + '": "s"}}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_import_side_refuses_the_same_blocks(self):
        for block in ('{"v": {"m": "' + "x" * 4096 + '"}}',
                      '{"v": {"' + "k" * 5000 + '": "s"}}',
                      '{"v": [{"' + "k" * 5000 + '": "s"}]}',
                      '{"v": {"' + "k" * 4090 + '": "'
                      + "x" * 10 + '"}}'):
            with self.subTest(block=block[:24]):
                self.assert_import_limit(block)

    def test_first_worked_form_stores_nothing_end_to_end(self):
        doc = '---\n{"v": {"m": "' + "x" * 4096 \
            + '"}}\n---\n# Heading\n\nbody\n'
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract_doc(doc)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")


class TestR9_019RemainingPunctuationPositions(Base):
    def test_line_form_red_eleven_characters(self):
        for char in ("=", ".", "-", "/", "@", "_", "`", "|", "~",
                     "+", "$"):
            with self.subTest(char=char):
                self.assert_page_refuses("title: x" + char + "&a")

    def test_line_form_remaining_twenty_one_characters(self):
        for char in ("!", "#", "$", "%", "&", "*", "+", "-", ".",
                     "/", "<", "=", ">", "?", "@", "\\", "^", "_",
                     "`", "|", "~"):
            with self.subTest(char=char):
                self.assert_page_refuses("title: x" + char + "&a")

    def test_json_form_sampled_characters(self):
        for char in (".", "/", "=", "|", "-", "_"):
            with self.subTest(char=char):
                self.assert_page_refuses(
                    '{"title": "x' + char + '&a"}')

    def test_construct_characters_beyond_the_anchor(self):
        for punct in (".", "/", "=", ">"):
            for construct in ("!", "*", "%"):
                with self.subTest(punct=punct, construct=construct):
                    self.assert_page_refuses(
                        "title: x" + punct + construct + "a")

    def test_line_form_key_position(self):
        self.assert_page_refuses("x.&a: abc")

    def test_json_form_key_position(self):
        self.assert_page_refuses('{"x.&a": "v"}')

    def test_cured_positions_and_plain_controls_stand(self):
        self.assert_page_refuses("title: a,!tag x")
        self.assert_page_refuses("title: {k:&b}")
        self.assertEqual(
            self.page_front_matter("title: abc"), "body text")
        self.assertEqual(
            self.page_front_matter('{"title": "abc"}'), "body text")


class TestR9_020TopLevelKeyMeasure(Base):
    def test_top_level_key_at_4097_refuses(self):
        block = '{"' + "k" * 4097 + '": "v"}'
        self.assert_page_limit(block)

    def test_top_level_key_at_5000_refuses(self):
        block = '{"' + "k" * 5000 + '": "v"}'
        self.assert_page_limit(block)

    def test_top_level_key_at_5000_holding_a_mapping_value(self):
        block = '{"' + "k" * 5000 + '": {"a": "b"}}'
        self.assert_page_limit(block)

    def test_top_level_key_of_4000_still_passes(self):
        block = '{"' + "k" * 4000 + '": "v"}'
        self.assertEqual(self.page_front_matter(block), "body text")

    def test_value_of_5000_inside_a_list_still_refuses(self):
        block = '{"title": ["' + "x" * 5000 + '"]}'
        self.assert_page_limit(block)

    def test_top_level_key_form_stores_nothing_end_to_end(self):
        doc = '---\n{"' + "k" * 5000 \
            + '": "v"}\n---\n# Heading\n\nbody\n'
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.extract_doc(doc)
        self.assertEqual(_token(caught.exception), "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
