"""Slice S2 acquisition and extraction tests, Step 13, Citeline.

Written before the product exists. Every test imports the
product package citeline and calls the acquisition
operations under the names the plan states (plan Section
5.3 module boundary row for S2, module acquisition, with
TextSegmentation as a named sub module inside it, trade
T-1). Import or attribute failure is the expected red
state. No stub and no mock of the product stands in this
file. Dates are call inputs, never clock reads.
"""

import fcntl
import hashlib
import os
import tempfile
import time
import unittest

from citeline import acquisition, journal, service

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
CORPUS = os.path.join(FIXTURES, "o5-11-corpus")
AUDIT_DATE = "2026-11-14"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def fixture(name):
    return os.path.join(FIXTURES, name)


def corpus(name):
    return os.path.join(CORPUS, name)


class AcquisitionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def extract(self, path, **kwargs):
        kwargs.setdefault("audit_date", AUDIT_DATE)
        return acquisition.extract_page(self.home, product_id="p-example", page_path=path, **kwargs)

    def journal_file(self):
        """Locate the home journal file by its entry content, on
        the surface the S5 module uses for the same states."""
        for root, _dirs, files in os.walk(self.home):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as handle:
                    data = handle.read()
                if b"entry_kind" in data:
                    return path, data
        raise AssertionError("no journal file found in home")

    def seed_journal(self):
        self.extract(corpus("fixture-page.txt"))
        return self.journal_file()


class TestFormatDetection(AcquisitionBase):
    def test_content_first_html_beats_extension(self):
        """Plan Section 1.3 S2, format detection in its stated order, and plan Section 5.4 detection rule. Oracle: brief Section 5.9 item 6 and Section 6.4, content first, declared format second, extension last; a file whose own leading content is an HTML document stands detected as html ahead of its extension."""
        result = self.extract(fixture("declared-mismatch.md"))
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "detected_format"), "html")
        self.assertEqual(field(snapshot, "format"), "html")

    def test_declared_format_second(self):
        """Plan Section 1.3 S2, format detection order. Oracle: brief Section 5.9 item 6, operator declared format stands second, after content and before extension."""
        result = acquisition.detect_format(b"Fixture Page Title\n\nPlain body text.\n", declared_format="markdown", filename="page.txt")
        self.assertEqual(field(result, "detected_format"), "markdown")

    def test_extension_last(self):
        """Plan Section 1.3 S2, format detection order. Oracle: brief Section 5.9 item 6, file name extension stands last in the detection order."""
        result = acquisition.detect_format(b"Fixture Page Title\n\nPlain body text.\n", declared_format=None, filename="page.md")
        self.assertEqual(field(result, "detected_format"), "markdown")

    def test_declared_detected_recorded_separately(self):
        """Plan Section 5.1 PageSnapshot shape. Oracle: brief Section 5.9 item 6, declared format and detected format stand recorded as separate values on the snapshot."""
        result = self.extract(corpus("fixture-page.md"), declared_format="text")
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "declared_format"), "text")
        self.assertEqual(field(snapshot, "detected_format"), "markdown")

    def test_disagreement_warning_travels(self):
        """Plan Section 1.3 S2, format detection. Oracle: brief Section 6.4 item 159 format limb, where declared and detected disagree a recorded warning is required, the detected format governs, and the warning travels with the snapshot record."""
        result = self.extract(corpus("fixture-page.md"), declared_format="text")
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "format"), "markdown")
        notes = field(field(result, "extracted"), "extraction_notes")
        self.assertTrue(notes)

    def test_fenced_html_does_not_decide_detection(self):
        """Plan Section 5.4 detection rule. Oracle: plan Section 5.4, material inside a fenced code block does not count as content for detection, and a complete HTML document appearing only inside a fence does not make the file html."""
        result = self.extract(fixture("fence-markdown.md"))
        self.assertEqual(field(field(result, "snapshot"), "detected_format"), "markdown")

    def test_blockquote_html_does_not_decide_detection(self):
        """Plan Section 5.4 detection rule. Oracle: plan Section 5.4, material inside a blockquote does not count as content for detection, and a complete HTML document appearing only inside a blockquote does not make the file html. Register entry R1-027."""
        result = self.extract(fixture("blockquote-html.md"))
        self.assertEqual(field(field(result, "snapshot"), "detected_format"), "markdown")

    def test_xhtml_container_fails_despite_html_signals(self):
        """Plan Section 5.4 container precedence and XHTML marker test. Oracle: brief Section 5.9 item 100 and Section 6.4 item 100, XHTML is a hard failure, and the container rule stands ahead of content detection."""
        with self.assertRaises(Exception):
            self.extract(fixture("xhtml-page.html"))

    def test_xhtml_doctype_marker_alone_fails(self):
        """Plan Section 5.4 XHTML marker test. Oracle: plan Section 5.4, one marker suffices, a doctype declaration naming XHTML alone marks the file as XHTML and the container rule fails it. Register entry R1-032."""
        with self.assertRaises(Exception):
            self.extract(fixture("xhtml-doctype-only.html"))

    def test_xhtml_namespace_marker_alone_fails(self):
        """Plan Section 5.4 XHTML marker test. Oracle: plan Section 5.4, one marker suffices, the XHTML namespace declared on the root element alone marks the file as XHTML and the container rule fails it. Register entry R1-032."""
        with self.assertRaises(Exception):
            self.extract(fixture("xhtml-namespace-only.html"))

    def test_mhtml_container_fails_despite_html_signals(self):
        """Plan Section 5.4 container precedence. Oracle: plan Section 5.4, the same precedence holds for the MHTML container form over any content signal its inner material carries. Register entry R1-032."""
        with self.assertRaises(Exception):
            self.extract(fixture("mhtml-container.mht"))

    def test_ambiguous_detection_fails(self):
        """Plan Section 1.3 S2, format detection. Oracle: brief Section 6.4, where detection is ambiguous the outcome is a recorded error and no score and no report for that file; plan entry 13 row X-14 names ambiguous format detection."""
        with self.assertRaises(Exception):
            acquisition.detect_format(b"\x00\x01\x02 binary residue", declared_format=None, filename="page.bin")


class TestDecodingAndStructure(AcquisitionBase):
    def test_bom_stripped_once_and_noted(self):
        """Plan Section 1.3 S2, decoding rules. Oracle: brief Section 5.9 item 99 and plan Section 5.4, a single leading UTF-8 byte order mark is stripped once before decoding and recorded as an extraction note."""
        result = self.extract(fixture("bom-page.txt"))
        extracted = field(result, "extracted")
        self.assertTrue(field(extracted, "extraction_notes"))
        self.assertFalse(field(extracted, "running_text").startswith("\ufeff"))

    def test_second_bom_is_ordinary_character(self):
        """Plan Section 5.4, second or later byte order mark. Oracle: plan Section 5.4, after the single strip any further byte order mark stands in the decoded text as an ordinary U+FEFF character and counts toward character limits."""
        raw = b"\xef\xbb\xbf\xef\xbb\xbfBody text stands here.\n"
        path = os.path.join(self.tmp.name, "two-bom.txt")
        with open(path, "wb") as handle:
            handle.write(raw)
        result = self.extract(path)
        self.assertIn("\ufeff", field(field(result, "extracted"), "running_text"))

    def test_invalid_utf8_fails_closed(self):
        """Plan Section 1.3 S2, decoding rules. Oracle: brief Section 5.9 parser failure table and item 99, undecodable bytes and invalid UTF-8 fail closed with a recorded error and nothing stored; row X-14."""
        path = os.path.join(self.tmp.name, "bad.txt")
        with open(path, "wb") as handle:
            handle.write(b"\xff\xfe invalid bytes")
        with self.assertRaises(Exception):
            self.extract(path)

    def test_unclosed_script_fails_closed(self):
        """Plan Section 1.3 S2, structure rules. Oracle: brief Section 5.9 parser failure table, an unclosed script or style element fails closed with a recorded error and nothing stored."""
        with self.assertRaises(Exception):
            self.extract(fixture("unclosed-script.html"))

    def test_unclosed_style_fails_closed(self):
        """Plan Section 1.3 S2, structure rules. Oracle: brief Section 5.9 parser failure table, an unclosed style element fails closed with a recorded error and nothing stored. Register entry R1-026."""
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(fixture("unclosed-style.html"))
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_ambiguous_script_content_fails_closed(self):
        """Plan Section 1.3 S2, structure rules. Oracle: brief Section 5.9 parser failure table, any case where content inside a script element could be counted or excluded ambiguously fails closed with a recorded error and nothing stored; the fixture script holds a closing tag inside a string, so its content stands ambiguous. Register entry R1-026."""
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(fixture("ambiguous-script.html"))
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_front_matter_failing_d17_controls_fails_closed(self):
        """Plan Section 1.3 S2, structure rules. Oracle: brief Section 5.9 parser failure table, front matter that fails the D17 control set fails closed with a recorded error and nothing stored; the D17 set rejects tag constructs in front matter, and the fixture front matter carries one. Register entry R1-026."""
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(fixture("frontmatter-tag.md"))
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_recoverable_classes_extracted_with_notes(self):
        """Plan Section 1.3 S2, structure rules. Oracle: brief Section 5.9 parser failure table, extraction with notes for the recoverable classes only, an unclosed inline formatting element extracted as written, a stray closing tag dropped, and an attribute with no value or an unquoted value read as written."""
        result = self.extract(fixture("recoverable.html"))
        extracted = field(result, "extracted")
        self.assertIn("unclosed inline emphasis", field(extracted, "running_text"))
        self.assertIn("Second para text.", field(extracted, "running_text"))
        self.assertTrue(field(extracted, "extraction_notes"))

    def test_recoverable_unresolved_markdown_reference(self):
        """Plan Section 1.3 S2, structure rules, unresolved Markdown references class. Oracle: brief Section 5.9 parser failure table, the reference text is extracted as written and no target is extracted from it. Register entry R1-025."""
        result = self.extract(fixture("recoverable-refs.md"))
        extracted = field(result, "extracted")
        self.assertIn("the reference text", field(extracted, "running_text"))
        for link in field(extracted, "links"):
            self.assertNotEqual(field(link, "text"), "the reference text")
            self.assertNotEqual(field(link, "target"), "missing-ref")
        self.assertTrue(field(extracted, "extraction_notes"))

    def test_recoverable_duplicate_headings(self):
        """Plan Section 1.3 S2, structure rules, duplicate headings class. Oracle: brief Section 5.9 parser failure table, each duplicate heading is extracted as written and each stands as a heading in its own position. Register entry R1-025."""
        result = self.extract(fixture("dup-headings.md"))
        extracted = field(result, "extracted")
        headings = []
        for heading in field(extracted, "headings"):
            if isinstance(heading, dict) or hasattr(heading, "text"):
                headings.append(field(heading, "text"))
            else:
                headings.append(heading)
        self.assertEqual(headings, ["Repeat Heading", "Repeat Heading"])
        self.assertTrue(field(extracted, "extraction_notes"))

    def test_snapshot_identity_fields(self):
        """Plan Section 5.1 PageSnapshot shape. Oracle: plan Section 5.1, the snapshot carries sha256 of the raw bytes and byte_size, and snapshot identity travels beside a page score."""
        with open(corpus("fixture-page.txt"), "rb") as handle:
            raw = handle.read()
        result = self.extract(corpus("fixture-page.txt"))
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "sha256"), hashlib.sha256(raw).hexdigest())
        self.assertEqual(field(snapshot, "byte_size"), len(raw))
        self.assertEqual(field(snapshot, "byte_size"), 359)

    def test_is_product_page_initial_false(self):
        """Plan Section 5.1 PageSnapshot shape, sole writer discipline limb inside S2. Oracle: plan Section 5.1, S2 writes false as the initial value of is_product_page at creation and S1 is sole writer after creation."""
        result = self.extract(corpus("fixture-page.txt"))
        self.assertFalse(field(field(result, "snapshot"), "is_product_page"))


class TestSegmentation(AcquisitionBase):
    def segment(self, name):
        with open(fixture(name), encoding="utf-8") as handle:
            text = handle.read()
        fmt = "markdown" if name.endswith(".md") else "text"
        return acquisition.segment_text(text, format=fmt)

    def test_sentence_terminal_mark(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154 segmentation rules, a sentence ends at a terminal mark plus a following space or the end of the text."""
        seg = self.segment("seg-text.txt")
        sentences = field(seg, "sentences")
        self.assertEqual(sentences[0], "First line block has one sentence.")
        self.assertEqual(sentences[1], "And another one here.")

    def test_sentence_abbreviation_not_boundary(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154, the closed abbreviation list is Dr, Mr, Mrs, Ms, St, vs, e.g., i.e., and a mark inside one of those abbreviations is not a boundary."""
        seg = self.segment("seg-markdown.md")
        sentences = field(seg, "sentences")
        self.assertIn("Dr. Patel paid 3.50 for the guide.", sentences)
        self.assertIn("Mr. Lee agreed.", sentences)

    def test_sentence_decimal_not_boundary(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154, a full stop between digits in a decimal or a version string is not a boundary."""
        seg = self.segment("seg-markdown.md")
        joined = " ".join(field(seg, "sentences"))
        self.assertIn("3.50", joined)
        self.assertNotIn("Dr. Patel paid 3.", field(seg, "sentences"))

    def test_sentence_ellipsis_one_mark(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154, an ellipsis counts as one terminal mark, so the terminal mark rule, a terminal mark plus a following space, gives one boundary after the ellipsis and the sentence stands as Wait... whole, not as fragments at each dot. The fixture sentence and this expectation stand changed under register entry R1-030 so the pinned case tests only that the ellipsis counts as one mark and not three; the course taken stands recorded in writer 2's paper by erratum."""
        seg = self.segment("seg-markdown.md")
        sentences = field(seg, "sentences")
        self.assertIn("Wait...", sentences)
        self.assertIn("Then she paused.", sentences)
        self.assertNotIn("Wait.", sentences)
        self.assertNotIn("Wait..", sentences)

    def test_sentence_closing_quote_belongs(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154, where a closing quotation mark intervenes the boundary falls after the closing mark, so the closing mark belongs to the sentence it closes."""
        seg = self.segment("seg-markdown.md")
        self.assertIn('She said "Done."', field(seg, "sentences"))

    def test_sentence_link_target_masked(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sentences. Oracle: brief Section 5.1 item 154, link and URL spans are masked before splitting, so a sentence boundary inside a target cannot split a sentence."""
        seg = acquisition.segment_text("See [the guide](https://example.invalid/a.b) for details. Next sentence stands.", format="markdown")
        self.assertEqual(len(field(seg, "sentences")), 2)

    def test_paragraphs_markdown_blank_line(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, paragraphs, Markdown limb. Oracle: brief Section 5.1 item 154, a paragraph in Markdown or text is a block of running text separated from the next block by a blank line."""
        seg = self.segment("seg-markdown.md")
        paragraphs = [p for p in field(seg, "paragraphs") if "Dr. Patel" in p]
        self.assertEqual(len(paragraphs), 1)
        self.assertIn("It worked well.", paragraphs[0])

    def test_paragraphs_text_blank_line(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, paragraphs, text limb. Oracle: brief Section 5.1 item 154, blank line separation in text, and brief Section 5.9 item 107, leading and trailing blank lines form no paragraph."""
        seg = self.segment("seg-text.txt")
        self.assertEqual(len(field(seg, "paragraphs")), 2)

    def test_text_no_line_breaks_one_block(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, paragraphs, text limb. Oracle: brief Section 5.9 item 107 decision three, a text file with no line breaks is one block for segmentation."""
        seg = self.segment("seg-single-block.txt")
        self.assertEqual(len(field(seg, "paragraphs")), 1)

    def test_sections_from_headings(self):
        """Plan Section 1.3 S2, TextSegmentation outputs, sections. Oracle: plan Section 5.1 ExtractedPage, sections are the section map with heading offset range and heading text as display only."""
        seg = self.segment("seg-markdown.md")
        sections = field(seg, "sections")
        texts = [field(s, "heading_text") for s in sections]
        self.assertIn("Alpha Section", texts)
        self.assertIn("Beta Section", texts)

    def test_segmentation_pinned_before_checks(self):
        """Plan Section 1.3 S2, TextSegmentation outputs pinned before any S3 check consumes them. Oracle: brief Section 5.1 item 154, segmentation test cases are pinned before the checks that rest on it, and every consumer consumes this component output and no other segmentation."""
        result = self.extract(fixture("seg-markdown.md"))
        extracted = field(result, "extracted")
        seg = self.segment("seg-markdown.md")
        self.assertEqual(field(extracted, "sentences"), field(seg, "sentences"))
        self.assertEqual(field(extracted, "paragraphs"), field(seg, "paragraphs"))


class TestExtractionEndStates(AcquisitionBase):
    def test_ok_stored(self):
        """Plan Section 1.3 S2, extraction end states. Oracle: brief Section 5.9, extraction end states, ok is stored and audited; contract C8 extraction limb."""
        result = self.extract(corpus("fixture-page.html"))
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "extraction_outcome"), "ok")
        self.assertTrue(field(snapshot, "snapshot_id"))

    def test_empty_stored_with_audit_record(self):
        """Plan Section 1.3 S2, extraction end states, decided limbs of the severed empty page case. Oracle: brief Section 5.9, empty is stored, the audit record is produced, and every check reports not_applicable. The score expectation stands blocked at B4 on K-20 and no score is asserted here."""
        result = service.audit(home=self.home, page_file=fixture("empty-page.txt"), audit_date=AUDIT_DATE)
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "extraction_outcome"), "empty")
        run = field(result, "audit_run")
        self.assertTrue(run)
        for check in field(run, "checks"):
            self.assertEqual(field(check, "status"), "not_applicable")

    def test_empty_reason_code(self):
        """Plan Section 1.3 S2, extraction end states, decided limb. Oracle: plan Section 5.1 PageSnapshot, extraction_outcome empty carries the Section 5.7 reason code EXT_EMPTY."""
        result = self.extract(fixture("empty-page.txt"))
        snapshot = field(result, "snapshot")
        self.assertEqual(field(snapshot, "extraction_outcome"), "empty")
        self.assertEqual(field(snapshot, "reason_code"), "EXT_EMPTY")

    def test_failed_not_stored_call_fails(self):
        """Plan Section 1.3 S2, extraction end states. Oracle: brief Section 5.9, failed is not stored at all, the call fails with a recorded error, and no audit record stands."""
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(fixture("unclosed-script.html"))
        after = set(os.listdir(self.home))
        self.assertEqual(before, after)

    def test_failed_one_failure_record_where_chain_accepts(self):
        """Plan Section 1.3 S2, extraction end states. Oracle: brief Section 5.9 item 158 scope, a failed operation the process lives to report leaves exactly one failure record entry and no subject entry, scoped to chains that accept appends."""
        result = acquisition.extract_page_reporting(self.home, product_id="p-example", page_path=fixture("unclosed-script.html"), audit_date=AUDIT_DATE)
        self.assertEqual(len(field(result, "failure_records")), 1)
        self.assertIsNone(field(result, "snapshot"))


    def test_failed_no_failure_record_where_chain_barred(self):
        """Plan Section 1.3 S2, extraction end states, EC-13 excepted limb. Oracle: brief Section 5.9 item 158 scope and plan entry 13 row I-2, on a barred chain no failure record can be appended and the recorded error stands as caller response only. Arranged on the home level surface the S0 and S5 modules use: a line that is not a journal entry stands appended to the journal file, then the failing extraction is attempted. Register entry R1-033."""
        path, _data = self.seed_journal()
        with open(path, "ab") as handle:
            handle.write(b"this line is not a journal entry\n")
        with open(path, "rb") as handle:
            before = handle.read()
        with self.assertRaises(Exception):
            self.extract(fixture("unclosed-script.html"))
        with open(path, "rb") as handle:
            after = handle.read()
        self.assertEqual(after, before)
        self.assertNotIn(b"failure_record", after)

    def test_failed_no_failure_record_where_chain_at_cap(self):
        """Plan Section 1.3 S2, extraction end states, EC-13 excepted limb. Oracle: brief Section 5.9 item 158 scope and plan entry 13 row I-1, at the cap no failure record can be appended and the recorded error stands as caller response only. Arranged on the surface the S0 module uses: journal_length stands lowered to the standing entry count through the product config writer. Register entry R1-033."""
        path, data = self.seed_journal()
        standing = len([line for line in data.splitlines() if line.strip()])
        journal.write_config(self.home, "journal_length = %d\n" % standing)
        with self.assertRaises(Exception):
            self.extract(fixture("unclosed-script.html"))
        with open(path, "rb") as handle:
            after = handle.read()
        self.assertEqual(after, data)
        self.assertNotIn(b"failure_record", after)

    def test_failed_no_failure_record_where_invocation_contended(self):
        """Plan Section 1.3 S2, extraction end states, EC-13 excepted limb. Oracle: brief Section 5.9 item 158 scope and plan entry 13 row X-10, a contended invocation leaves no failure record and the recorded error stands as caller response only. Arranged on the surface the S0 and S5 modules use: the advisory write lock file .citeline-write.lock in the home stands held under flock. Register entry R1-033."""
        path, data = self.seed_journal()
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        with open(lock_path, "w", encoding="utf-8") as handle:
            handle.write("")
        with open(lock_path, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Exception):
                self.extract(fixture("unclosed-script.html"))
            fcntl.flock(handle, fcntl.LOCK_UN)
        with open(path, "rb") as handle:
            after = handle.read()
        self.assertEqual(after, data)
        self.assertNotIn(b"failure_record", after)


class TestOpenProtocol(AcquisitionBase):
    def test_symlink_refused(self):
        """Plan Section 1.3 S2, supplied file open protocol in operating system terms. Oracle: brief Section 7.2 boundary B1 and item 115, a supplied path that is itself a symbolic link is rejected with a recorded error, detected by a stat that does not follow the final component before opening."""
        link = os.path.join(self.tmp.name, "link.txt")
        os.symlink(corpus("fixture-page.txt"), link)
        with self.assertRaises(Exception):
            self.extract(link)

    def test_directory_refused(self):
        """Plan Section 1.3 S2, supplied file open protocol. Oracle: brief Section 7.2 boundary B1, a path that does not name a regular file is rejected, a directory among them; plan entry 13 row X-4."""
        with self.assertRaises(Exception):
            self.extract(self.tmp.name)

    def test_fifo_refused_without_blocking(self):
        """Plan Section 1.3 S2, supplied file open protocol. Oracle: brief Section 7.2 boundary B1 non regular file rejection, read with the IM2-BRK-4 shape of answer, a non blocking no follow open so a FIFO cannot block the invocation forever."""
        fifo = os.path.join(self.tmp.name, "pipe.txt")
        os.mkfifo(fifo)
        start = time.monotonic()
        with self.assertRaises(Exception):
            self.extract(fifo)
        self.assertLess(time.monotonic() - start, 10.0)

    def test_hard_link_count_above_one_refused(self):
        """Plan Section 1.3 S2, supplied file open protocol, with entry 19 limit statement carried at this point. Oracle: brief Section 7.2 boundary B1, a supplied file with a hard link count above 1 is rejected with a recorded error. Entry 19 limit statement, carried here because the clause rests on it: this check rests on the filesystem maintaining a truthful link count, and where a platform cannot give that count the invocation refuses the supplied file and fails closed, with the limit stated instead of the check claimed."""
        target = os.path.join(self.tmp.name, "hard.txt")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("Body text stands here.\n")
        os.link(target, os.path.join(self.tmp.name, "hard-second.txt"))
        with self.assertRaises(Exception):
            self.extract(target)

    def test_opened_once_read_once(self):
        """Plan Section 1.3 S2, supplied file open protocol. Oracle: contract C8, the file stands opened once and read once, and no audit output mixes extraction from one reading with checks from another."""
        result = self.extract(corpus("fixture-page.html"))
        snapshot = field(result, "snapshot")
        with open(corpus("fixture-page.html"), "rb") as handle:
            raw = handle.read()
        self.assertEqual(field(snapshot, "sha256"), hashlib.sha256(raw).hexdigest())


class TestPageSideLimits(AcquisitionBase):
    def test_page_file_over_2mib_rejected_no_partial(self):
        """Plan Section 1.3 S2, page side limits enforcement with rejection and no partial record. Oracle: brief Section 5.11 limit 1, page file size 2 MiB, and items 57 and 98, rejection with a recorded error and no partial record, never truncated detection; row X-3."""
        path = os.path.join(self.tmp.name, "big.txt")
        with open(path, "wb") as handle:
            handle.write(b"a" * (2 * 1024 * 1024 + 1))
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(path)
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_extracted_text_limit_rejected(self):
        """Plan Section 1.3 S2, page side limits enforcement. Oracle: brief Section 5.11 limit 3, extracted text length per page 500,000 characters, with rejection and no partial record. Register entry R1-029: the home listing stands unchanged across the rejection, as the limit 1 sibling test pins."""
        path = os.path.join(self.tmp.name, "long.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("word " * 100001)
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(path)
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_element_event_limit_rejected_no_partial(self):
        """Plan Section 1.3 S2, page side limits enforcement. Oracle: brief Section 5.11 limit 4, element or tag events per page 100,000, with rejection and no partial record. Register entry R1-031."""
        path = os.path.join(self.tmp.name, "many-elements.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<html><body>" + "<span>x</span>" * 100001 + "</body></html>")
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(path)
        self.assertEqual(set(os.listdir(self.home)), before)

    def test_nesting_depth_limit_rejected_no_partial(self):
        """Plan Section 1.3 S2, page side limits enforcement. Oracle: brief Section 5.11 limit 5, nesting depth 100, with rejection and no partial record. Register entry R1-031."""
        path = os.path.join(self.tmp.name, "deep.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<div>" * 101 + "Body text." + "</div>" * 101)
        before = set(os.listdir(self.home))
        with self.assertRaises(Exception):
            self.extract(path)
        self.assertEqual(set(os.listdir(self.home)), before)


class TestFormInventory(AcquisitionBase):
    def test_html_corpus_all_forms(self):
        """Plan Section 1.3 S2, form inventory each extraction tag finds with its form, over the re-authored O5-11 corpus. Oracle: brief Section 5.3 contract 3 item 39, extraction owns the form inventory and tags each find with its form; expectations hand computed from the corpus design in design/brief/step-06-o5-11-clerk-rerun.md, HTML file, 10 of 10 signals."""
        result = self.extract(corpus("fixture-page.html"))
        ex = field(result, "extracted")
        self.assertTrue(field(ex, "headings"))
        self.assertTrue(field(ex, "blockquotes"))
        self.assertTrue(field(ex, "lists"))
        self.assertTrue(field(ex, "tables"))
        self.assertTrue(field(ex, "date_strings"))
        self.assertIn("The reference sentence that must match verbatim.", field(ex, "running_text"))
        self.assertIn("42 of 100 pages carried the signal.", field(ex, "running_text"))
        self.assertIsNotNone(field(ex, "canonical_link_element"))
        self.assertIsNotNone(field(ex, "meta_robots"))
        links = field(ex, "links")
        self.assertEqual(field(links[0], "target"), "https://example.invalid/source")
        self.assertEqual(field(links[0], "text"), "Citation source text")

    def test_markdown_corpus_forms(self):
        """Plan Section 1.3 S2, form inventory, over the re-authored O5-11 corpus. Oracle: item 39 form inventory; expectations hand computed from the corpus design, Markdown file, 8 of 10 signals, the canonical link element and the meta robots directive not present."""
        result = self.extract(corpus("fixture-page.md"))
        ex = field(result, "extracted")
        self.assertTrue(field(ex, "headings"))
        self.assertTrue(field(ex, "blockquotes"))
        self.assertTrue(field(ex, "lists"))
        self.assertTrue(field(ex, "tables"))
        self.assertTrue(field(ex, "date_strings"))
        self.assertIn("The reference sentence that must match verbatim.", field(ex, "running_text"))
        self.assertIn("42 of 100 pages carried the signal.", field(ex, "running_text"))
        links = field(ex, "links")
        self.assertEqual(field(links[0], "target"), "https://example.invalid/source")
        self.assertEqual(field(links[0], "text"), "Citation source text")
        self.assertIsNone(field(ex, "canonical_link_element"))
        self.assertIsNone(field(ex, "meta_robots"))

    def test_text_corpus_forms(self):
        """Plan Section 1.3 S2, form inventory, over the re-authored O5-11 corpus. Oracle: item 39 form inventory; expectations hand computed from the corpus design, text file, 3 of 10 signals, the date string, the canonical line verbatim, and the statistic sentence as running text only, with no structure, marking, or link form."""
        result = self.extract(corpus("fixture-page.txt"))
        ex = field(result, "extracted")
        self.assertTrue(field(ex, "date_strings"))
        self.assertIn("The reference sentence that must match verbatim.", field(ex, "running_text"))
        self.assertIn("42 of 100 pages carried the signal.", field(ex, "running_text"))
        self.assertFalse(field(ex, "headings"))
        self.assertFalse(field(ex, "blockquotes"))
        self.assertFalse(field(ex, "lists"))
        self.assertFalse(field(ex, "tables"))
        self.assertFalse(field(ex, "links"))
        self.assertIsNone(field(ex, "canonical_link_element"))
        self.assertIsNone(field(ex, "meta_robots"))

    def test_corpus_word_counts_hand_computed(self):
        """Plan Section 1.3 S2, form inventory and segmentation over the re-authored O5-11 corpus. Oracle: brief Section 5.1 item 154 word tokenisation, words are alphanumeric tokens, a hyphenated form counts as its parts, a decimal counts as one word. Expectation source: hand count of the text corpus running text at re-authoring."""
        result = self.extract(corpus("fixture-page.txt"))
        ex = field(result, "extracted")
        self.assertEqual(field(ex, "word_count"), 60)
        self.assertEqual(field(ex, "extracted_text_length"), len(field(ex, "running_text")))

    def test_extraction_timing_bound(self):
        """Plan Section 1.5 timing bounds, S2. Oracle: acquisition, extraction, and segmentation over one supplied page at the brief page limits, 10 seconds. Scale: the re-authored O5-11 HTML corpus page."""
        start = time.monotonic()
        self.extract(corpus("fixture-page.html"))
        self.assertLess(time.monotonic() - start, 10.0)


if __name__ == "__main__":
    unittest.main()
