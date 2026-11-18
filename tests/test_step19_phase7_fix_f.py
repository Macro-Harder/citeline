"""Repair tests: import and page intake.

Each class pins one repair finding from the attack findings
(the audit record Tests were written
before the fixes they pin. the settled rule stands routed as a
design question and carries no cure test in this file.
"""

import json
import unittest

from citeline import acquisition, probe_import

ANSWER = "Acme Ledger is the bookkeeping tool I use every week."


def form_of(text):
    return probe_import.check11_form(text.encode("utf-8"), text)


class TestP7A201HtmlByDocumentKind(unittest.TestCase):
    """The settled rule: an HTML capture is refused in every spelling,
    judged by document kind: a file whose first content unit is
    markup is an HTML document or fragment, not answer text."""

    SPELLINGS = {
        "script": "<script>var x = 1;</script>\n<p>" + ANSWER + "</p>",
        "script_only": "<script type=\"text/javascript\">alert(1)</script> "
                       + ANSWER,
        "style": "<style>body { color: red; }</style>\n<p>" + ANSWER + "</p>",
        "meta_then_document": "<meta charset=\"utf-8\">\n"
                              "<html><head><title>t</title></head>"
                              "<body>" + ANSWER + "</body></html>",
        "link": "<link rel=\"stylesheet\" href=\"a.css\">\n<p>" + ANSWER + "</p>",
        "base": "<base href=\"https://x.example/\">\n<p>" + ANSWER + "</p>",
        "template": "<template><p>" + ANSWER + "</p></template>",
        "noscript": "<noscript><p>" + ANSWER + "</p></noscript>",
        "textarea": "<textarea>" + ANSWER + "</textarea>",
        "math": "<math><mi>x</mi><annotation>" + ANSWER
                + "</annotation></math>",
        "strong": "<strong>" + ANSWER + "</strong>",
        "select": "<select><option>" + ANSWER + "</option></select>",
        "dl": "<dl><dt>term</dt><dd>" + ANSWER + "</dd></dl>",
        "fieldset": "<fieldset><p>" + ANSWER + "</p></fieldset>",
        "picture": "<picture><source srcset=\"a.png\"><p>" + ANSWER
                   + "</p></picture>",
        "custom_element": "<chat-export><p>" + ANSWER + "</p></chat-export>",
        "prolog_then_script": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                              "<script>alert(1)</script><p>" + ANSWER + "</p>",
        "comment_then_style": "<!-- export -->\n<style>p{}</style><p>"
                              + ANSWER + "</p>",
        "header_line_then_document": "Exported answer below.\n"
                                     "<html><body>" + ANSWER
                                     + "</body></html>",
        "cdata_document": "<![CDATA[ <html><body>" + ANSWER
                          + "</body></html> ]]>",
    }

    def test_attack_spellings_are_html_form(self):
        for name, text in self.SPELLINGS.items():
            with self.subTest(spelling=name):
                self.assertEqual(form_of(text), "html")

    def test_cured_spellings_still_hold(self):
        held = {
            "doctype": "<!DOCTYPE html>\n<html><body>" + ANSWER
                       + "</body></html>",
            "prolog_doctype": "<?xml version=\"1.0\"?>\n<!DOCTYPE html>\n"
                              "<html><body>" + ANSWER + "</body></html>",
            "saved_from": "<!-- saved from url=(0023)https://chat.example.com/ -->\n"
                          "<html><body>" + ANSWER + "</body></html>",
            "div_fragment": "<div class=\"answer\"><p>" + ANSWER + "</p></div>",
            "iframe_fragment": "<iframe src=\"a.html\"></iframe>" + ANSWER,
            "doctype_internal_subset": "<!DOCTYPE html [ <!ENTITY x \"y\"> ]>\n"
                                       "<html><body>" + ANSWER
                                       + "</body></html>",
        }
        for name, text in held.items():
            with self.subTest(spelling=name):
                self.assertEqual(form_of(text), "html")

    def test_plain_prose_is_not_html(self):
        self.assertIsNone(form_of(ANSWER))
        self.assertIsNone(form_of(
            "Ratings: 5 < 6 and 7 > 2, said the reviewer.\n" + ANSWER))

    def test_prose_quoting_a_tag_mid_text_is_not_html(self):
        text = ("The guide mentions the div element and the script "
                "element by name.\n" + ANSWER)
        self.assertIsNone(form_of(text))


class TestP7A202JsonLinesPastTheTenth(unittest.TestCase):
    """The settled rule: a JSON lines export stands as json_lines where
    its JSON lines are the substance of the file, however its
    framing, fencing, or damage is spelled, and not only where
    the non JSON lines stay within a tenth of the file."""

    @staticmethod
    def lines(count):
        return [json.dumps({"answer": "answer %d" % i})
                for i in range(count)]

    def test_header_and_truncated_tail_19_lines(self):
        body = self.lines(17)
        text = "# Exported from ChatGPT\n" + "\n".join(body) \
            + "\n{\"answer\": \"cut off mid"
        self.assertEqual(form_of(text), "json_lines")

    def test_header_and_footer_15_lines(self):
        text = "# Exported from ChatGPT\n" + "\n".join(self.lines(13)) \
            + "\nEnd of export\n"
        self.assertEqual(form_of(text), "json_lines")

    def test_code_fenced_12_lines(self):
        text = "```json\n" + "\n".join(self.lines(10)) + "\n```\n"
        self.assertEqual(form_of(text), "json_lines")

    def test_eleven_lines_two_framing(self):
        text = "Export header\n" + "\n".join(self.lines(9)) \
            + "\nExport footer"
        self.assertEqual(form_of(text), "json_lines")

    def test_hundred_lines_eleven_non_json(self):
        rows = self.lines(89)
        text = "\n".join(rows[:5] + ["not json"] * 11 + rows[5:])
        self.assertEqual(form_of(text), "json_lines")

    def test_boundary_spellings_still_hold(self):
        rows = self.lines(18)
        text = "header\n" + "\n".join(rows) + "\nfooter"
        self.assertEqual(form_of(text), "json_lines")
        self.assertEqual(form_of("\n".join(self.lines(50))), "json_lines")

    def test_plain_prose_is_not_json_lines(self):
        text = ("Acme Ledger is a bookkeeping tool.\n"
                "It tracks citations for a page.\n"
                "Teams use it every week.")
        self.assertNotEqual(form_of(text), "json_lines")

    def test_prose_with_an_incidental_json_line_is_not_json_lines(self):
        text = ("The export format looks like this:\n"
                "{\"answer\": \"one example line\"}\n"
                "Everything else in this answer is plain prose.\n"
                "It goes on for several more lines of prose.\n"
                "None of those lines is JSON at all.")
        self.assertNotEqual(form_of(text), "json_lines")


class TestP7A203TextPageFrontMatterControlSet(unittest.TestCase):
    """The settled rule: the text page intake enforces the whole front
    matter control set, as the import intake and the markdown
    page intake each enforce it on the identical block."""

    BODY = "# Acme Ledger\n\nAcme Ledger is a bookkeeping tool.\n"

    BLOCKS = {
        "duplicate_keys": "---\nkey: one\nkey: two\n---\n",
        "key_count_101": "---\n" + "".join(
            "k%d: v\n" % i for i in range(101)) + "---\n",
        "key_count_900": "---\n" + "".join(
            "k%d: v%d\n" % (i, i) for i in range(900)) + "---\n",
        "long_value_5000": "---\nkey: " + "v" * 5000 + "\n---\n",
        "json_duplicate_keys": "---\n{\"k\": 1, \"k\": 2}\n---\n",
        "json_unicode_escaped_tag": "---\n{\"k\": \"\\u0026a value\"}\n---\n",
    }

    def test_import_and_markdown_refuse_each_block(self):
        for name, block in self.BLOCKS.items():
            with self.subTest(block=name, intake="import"):
                with self.assertRaises(Exception):
                    probe_import.extract_front_matter(block + ANSWER)
            with self.subTest(block=name, intake="markdown"):
                with self.assertRaises(Exception):
                    acquisition._front_matter(
                        block + self.BODY, "markdown", [])

    def test_text_page_refuses_each_block(self):
        for name, block in self.BLOCKS.items():
            with self.subTest(block=name, intake="text"):
                with self.assertRaises(Exception):
                    acquisition._front_matter(
                        block + self.BODY, "text", [])

    def test_text_page_clean_block_still_admitted(self):
        notes = []
        result = acquisition._front_matter(
            "---\nkey: plain value\n---\n" + self.BODY, "text", notes)
        self.assertIn("Acme Ledger is a bookkeeping tool.", result)


class TestP7A204UnclosedFrontMatter(unittest.TestCase):
    """The settled rule: an unclosed head front matter block refuses at
    every intake, as the import intake refuses it."""

    UNCLOSED = "---\nkey: &a value\n"
    BODY = "# Acme Ledger\n\nAcme Ledger is a bookkeeping tool.\n"

    def test_import_refuses_unclosed(self):
        with self.assertRaises(Exception):
            probe_import.extract_front_matter(self.UNCLOSED + ANSWER)

    def test_text_page_refuses_unclosed(self):
        with self.assertRaises(Exception):
            acquisition._front_matter(self.UNCLOSED + self.BODY, "text", [])

    def test_markdown_page_refuses_unclosed(self):
        with self.assertRaises(Exception):
            acquisition._front_matter(
                self.UNCLOSED + self.BODY, "markdown", [])

    def test_plain_text_page_without_block_unchanged(self):
        notes = []
        result = acquisition._front_matter(self.BODY, "text", notes)
        self.assertEqual(result, self.BODY)


if __name__ == "__main__":
    unittest.main()
