"""The script and style gate reads a page on the module's
own stated rules, so its outcomes hold regardless of how
the interpreter's HTML parser reads a spelling: comment
forms never shield an unclosed script, the closing
spellings close, and a quoted bracket inside a closing
tag does not end the tag early."""

import unittest

from citeline import acquisition


def gate_fails(text):
    try:
        acquisition._check_script_style(text)
    except acquisition.AcquisitionError:
        return True
    return False


class ScriptStyleGateReadingTests(unittest.TestCase):
    def test_bang_closed_comment_does_not_shield_unclosed_script(self):
        self.assertTrue(gate_fails(
            "<html><body><!-- </script> --!><p>Before text.</p>"
            "<script>var x=1;<p>After swallowed text here.</p>"
            "</body></html>"))

    def test_abruptly_closed_comment_does_not_shield_script(self):
        for spelling in ("<!-->", "<!--->"):
            with self.subTest(spelling=spelling):
                self.assertTrue(gate_fails(
                    "<html><body>" + spelling
                    + "<p>Before text.</p>"
                    "<script>var x=1;<p>After swallowed text here.</p>"
                    "</body></html>"))

    def test_script_closed_with_slash_spelling_stands_closed(self):
        self.assertFalse(gate_fails(
            "<html><body><script>var x=1;</script/>"
            "<p>Real text here.</p></body></html>"))

    def test_script_closed_with_attribute_spelling_stands_closed(self):
        self.assertFalse(gate_fails(
            "<html><body><script>var x=1;</script foo>"
            "<p>Real text here.</p></body></html>"))

    def test_quoted_bracket_in_closing_tag_does_not_end_it_early(self):
        self.assertFalse(gate_fails(
            '<script>var x=1;</script foo="a> b">'
            "<html><body><p>Real text here.</p></body></html>"))

    def test_quoted_self_close_spelling_still_opens(self):
        self.assertTrue(gate_fails(
            "<html><body><p>Before text here.</p>"
            "<script data-x=\"/>\">var x=1;"
            "<p>After swallowed text here.</p></body></html>"))

    def test_unquoted_value_trailing_slash_opens(self):
        self.assertFalse(gate_fails(
            "<script src=x/>var x = 1;</script>"
            "<html><body><p>Real text here.</p></body></html>"))

    def test_spaced_slash_opens(self):
        self.assertFalse(gate_fails(
            "<script / >var x = 1;</script>"
            "<html><body><p>Real text here.</p></body></html>"))

    def test_comment_shape_inside_script_body_fails_closed(self):
        self.assertTrue(gate_fails(
            "<html><body><script><!-- </script> --></script>"
            "<p>Real text here.</p></body></html>"))

    def test_comment_opening_inside_attribute_is_not_a_comment(self):
        self.assertTrue(gate_fails(
            "<html><body><p title=\"<!--\">x</p> </script>"
            "<script>var x=1;<p>After swallowed text here.</p>"
            "</body></html>"))

    def test_plain_closed_script_and_style_pass(self):
        self.assertFalse(gate_fails(
            "<html><head><style>.a { color: red; }</style></head>"
            "<body><script>var x = 1;</script>"
            "<p>Real text here.</p></body></html>"))


if __name__ == "__main__":
    unittest.main()
