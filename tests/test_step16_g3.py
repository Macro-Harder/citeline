"""Step 16 supplementary fix wave, builder G3: heading location.

Defect pinned here:
E-03, heading location finds an earlier prose occurrence of the
heading text (finding S16-R2-S2-01). Where a later heading text
also stands in earlier body prose, the heading start and the
section map locate the prose occurrence instead of the heading
block, in both Markdown and HTML. The two controlled cases are
the round 2 S2 paper cases, stated in full there:

Case 1: blocks Title Page at 0, the prose sentence Evidence is
mentioned in this opening sentence at 12, the heading block
Evidence at 61, the last body block at 71, running text 101
characters. The defective product reported Evidence at 12 and
sections 0 to 12 and 12 to 101.

Case 2: blocks Opening at 0, the prose sentence The Final Notes
section is previewed here in prose at 9, the heading block
Final Notes at 62, running text 93 characters. The defective
product reported Final Notes at 13 and sections 0 to 13 and
13 to 93.
"""

import tempfile
import unittest
from pathlib import Path

from citeline import acquisition

AUDIT_DATE = "2026-11-14"

CASE1_MD = (
    "# Title Page\n"
    "\n"
    "Evidence is mentioned in this opening sentence.\n"
    "\n"
    "## Evidence\n"
    "\n"
    "Body text follows the heading.\n"
)
CASE1_HTML = (
    "<h1>Title Page</h1>"
    "<p>Evidence is mentioned in this opening sentence.</p>"
    "<h2>Evidence</h2>"
    "<p>Body text follows the heading.</p>"
)
CASE1_TEXT = (
    "Title Page\n\n"
    "Evidence is mentioned in this opening sentence.\n\n"
    "Evidence\n\n"
    "Body text follows the heading."
)
CASE2_MD = (
    "# Opening\n"
    "\n"
    "The Final Notes section is previewed here in prose.\n"
    "\n"
    "## Final Notes\n"
    "\n"
    "Body text follows.\n"
)
CASE2_HTML = (
    "<h1>Opening</h1>"
    "<p>The Final Notes section is previewed here in prose.</p>"
    "<h2>Final Notes</h2>"
    "<p>Body text follows.</p>"
)
CASE2_TEXT = (
    "Opening\n\n"
    "The Final Notes section is previewed here in prose.\n\n"
    "Final Notes\n\n"
    "Body text follows."
)


class G3Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = str(Path(self.tmp.name) / "home")
        Path(self.home).mkdir()

    def extract(self, name, content):
        path = Path(self.tmp.name) / name
        path.write_text(content, encoding="utf-8")
        result = acquisition.extract_page(
            self.home, product_id="p-example", page_path=str(path),
            audit_date=AUDIT_DATE)
        return result["extracted"]


class TestCase1ProseAtSentenceHead(G3Base):
    """Case 1: the heading text stands at a sentence head in
    earlier prose. The heading block stands at 61, not at the
    prose occurrence at 12."""

    def check_case1(self, extracted):
        self.assertEqual(extracted["running_text"], CASE1_TEXT)
        self.assertEqual(len(extracted["running_text"]), 101)
        headings = extracted["headings"]
        self.assertEqual(
            [(h["text"], h["level"], h["start"]) for h in headings],
            [("Title Page", 1, 0), ("Evidence", 2, 61)])
        text = extracted["running_text"]
        self.assertEqual(text[61:61 + len("Evidence")], "Evidence")
        sections = extracted["sections"]
        self.assertEqual(
            [(s["heading_text"], s["start"], s["end"])
             for s in sections],
            [("Title Page", 0, 61), ("Evidence", 61, 101)])

    def test_case1_markdown(self):
        self.check_case1(self.extract("case1.md", CASE1_MD))

    def test_case1_html(self):
        self.check_case1(self.extract("case1.html", CASE1_HTML))


class TestCase2ProseMidSentence(G3Base):
    """Case 2: the heading text stands mid sentence in earlier
    prose. The heading block stands at 62, not at the prose
    occurrence at 13."""

    def check_case2(self, extracted):
        self.assertEqual(extracted["running_text"], CASE2_TEXT)
        self.assertEqual(len(extracted["running_text"]), 93)
        headings = extracted["headings"]
        self.assertEqual(
            [(h["text"], h["level"], h["start"]) for h in headings],
            [("Opening", 1, 0), ("Final Notes", 2, 62)])
        text = extracted["running_text"]
        self.assertEqual(
            text[62:62 + len("Final Notes")], "Final Notes")
        sections = extracted["sections"]
        self.assertEqual(
            [(s["heading_text"], s["start"], s["end"])
             for s in sections],
            [("Opening", 0, 62), ("Final Notes", 62, 93)])

    def test_case2_markdown(self):
        self.check_case2(self.extract("case2.md", CASE2_MD))

    def test_case2_html(self):
        self.check_case2(self.extract("case2.html", CASE2_HTML))


class TestSectionsFollowCarriedHeadingBlocks(G3Base):
    """The section map follows the heading block positions a
    caller carries in, even where the heading text also stands
    in earlier prose of the text under segmentation."""

    def test_sections_follow_carried_starts_case1(self):
        seg = acquisition.segment_text(
            CASE1_TEXT, format="markdown",
            headings=[
                {"text": "Title Page", "level": 1, "start": 0},
                {"text": "Evidence", "level": 2, "start": 61},
            ])
        sections = seg["sections"]
        self.assertEqual(
            [(s["heading_text"], s["start"], s["end"])
             for s in sections],
            [("Title Page", 0, 61), ("Evidence", 61, 101)])

    def test_sections_follow_carried_starts_case2(self):
        seg = acquisition.segment_text(
            CASE2_TEXT, format="html",
            headings=[
                {"text": "Opening", "level": 1, "start": 0},
                {"text": "Final Notes", "level": 2, "start": 62},
            ])
        sections = seg["sections"]
        self.assertEqual(
            [(s["heading_text"], s["start"], s["end"])
             for s in sections],
            [("Opening", 0, 62), ("Final Notes", 62, 93)])


if __name__ == "__main__":
    unittest.main()
