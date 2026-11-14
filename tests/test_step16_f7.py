"""Step 16 fix wave, builder F7: artefact forms, tables, acquisition.

Defects pinned here, one failing test first per defect:
D-10, Agentic form collapse and envelope contract fields.
D-13, crawler table evidence labels on rows 9, 12, 13, 14.
D-14, crawler table obedience statement and crawl delay position.
D-15, Markdown heading offsets in extracted text coordinates.
D-29, a second form of a standing audit renders the stored record.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from citeline import acquisition, reporting, robots, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Example Product"
CANONICAL = "Example Product answers questions with citations."
QUERY = "What is Example Product?"
PAGE = FIXTURES / "w7-page.md"
ANSWER = FIXTURES / "w6-answer-named-cited.txt"

DIRECT = "directly verified"
SECONDARY = "secondary transcription"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(home):
    service.add_product(
        home=str(home), name=PRODUCT, canonical_line=CANONICAL,
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[QUERY],
        audit_date=AUDIT_DATE)


def seed_round(home, label, declaration="all captured answers imported"):
    service.name_round(
        home=str(home), product=PRODUCT, round_label=label,
        importer_declaration=declaration,
        supplier_relation="supplied by the audited party",
        audit_date=AUDIT_DATE)
    service.probe_import(
        home=str(home), answer_file=str(ANSWER), product=PRODUCT,
        round=label, engine_label="engine-a", query=QUERY,
        kind="real_sample", captured_on="2026-11-10",
        capture_method="manual copy", audit_date=AUDIT_DATE)


def cli(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = shell.main(list(argv))
    return code, buffer.getvalue()


class F7Base(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self.home)


class TestD10AgenticEnvelope(F7Base):
    """D-10: every Agentic response carries the item 122 envelope
    with its contract fields, and no Agentic artefact stands byte
    identical to its Advanced artefact."""

    def test_envelope_contract_fields_on_probe_report(self):
        seed_round(self.home, "round-1")
        envelope = service.probe_report(
            home=str(self.home), product=PRODUCT, round="round-1",
            form="agentic", audit_date=AUDIT_DATE)
        self.assertIn("report", envelope)
        self.assertIn("schema_stamp", envelope)
        self.assertTrue(envelope["schema_stamp"])
        self.assertIn("status", envelope)
        self.assertTrue(envelope["status"])
        self.assertIn("honesty_sentence", envelope)
        self.assertIn("anchor_limit", envelope)
        self.assertIn("report_id", envelope)
        self.assertEqual(envelope["report_id"],
                         envelope["report"]["round_id"])

    def test_envelope_contract_fields_on_guide_render(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        draft = service.guide(
            home=str(self.home), run_id=record["run_id"],
            audit_date=AUDIT_DATE)
        envelope = reporting.render(draft, "agentic")
        for name in ("report", "schema_stamp", "status",
                     "honesty_sentence", "anchor_limit", "report_id"):
            self.assertIn(name, envelope)
        self.assertEqual(envelope["report_id"], draft["guide_id"])

    def test_envelope_contract_fields_on_audit_render(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        envelope = reporting.render(record, "agentic")
        for name in ("report", "schema_stamp", "status",
                     "honesty_sentence", "anchor_limit", "report_id"):
            self.assertIn(name, envelope)
        self.assertEqual(envelope["report_id"], record["run_id"])

    def test_status_and_verify_agentic_differ_from_advanced_cli(self):
        for command in ("status", "verify"):
            code_a, advanced = cli(
                [command, "--home", str(self.home),
                 "--form", "advanced"])
            code_g, agentic = cli(
                [command, "--home", str(self.home),
                 "--form", "agentic"])
            self.assertEqual(code_a, 0, command)
            self.assertEqual(code_g, 0, command)
            self.assertNotEqual(advanced, agentic, command)
            parsed = json.loads(agentic)
            for name in ("report", "schema_stamp", "status",
                         "honesty_sentence", "anchor_limit"):
                self.assertIn(name, parsed, command)

    def test_probe_trend_agentic_differs_from_advanced_cli(self):
        seed_round(self.home, "round-1")
        seed_round(self.home, "round-2")
        base = ["probe", "trend", "--home", str(self.home),
                "--product", PRODUCT, "--round_a", "round-1",
                "--round_b", "round-2", "--audit_date", AUDIT_DATE]
        code_a, advanced = cli(base + ["--form", "advanced"])
        code_g, agentic = cli(base + ["--form", "agentic"])
        self.assertEqual(code_a, 0)
        self.assertEqual(code_g, 0)
        self.assertNotEqual(advanced, agentic)
        parsed = json.loads(agentic)
        for name in ("report", "schema_stamp", "status",
                     "honesty_sentence", "anchor_limit"):
            self.assertIn(name, parsed)


class TestD13D14CrawlerTable(unittest.TestCase):
    """D-13 and D-14: the shipped crawler table rows carry the
    judged evidence labels and both stated fields per row."""

    def rows_by_number(self):
        return {row["row"]: row for row in robots.CRAWLER_TABLE}

    def test_rows_9_12_13_14_evidence_labels_direct(self):
        rows = self.rows_by_number()
        for number in (9, 12, 13, 14):
            self.assertEqual(rows[number]["evidence_label"], DIRECT,
                             "row %d" % number)

    def test_purpose_prose_labels_split(self):
        rows = self.rows_by_number()
        self.assertEqual(
            rows[9]["purpose_prose_evidence_label"], DIRECT)
        for number in (12, 13, 14):
            self.assertEqual(
                rows[number]["purpose_prose_evidence_label"],
                SECONDARY, "row %d" % number)
        for number, row in rows.items():
            if number not in (12, 13, 14):
                self.assertEqual(
                    row["purpose_prose_evidence_label"], DIRECT,
                    "row %d" % number)

    def test_report_findings_carry_direct_labels(self):
        report = robots.evaluate_robots_text(
            "User-agent: *\nAllow: /\n", evaluated_page_path="/")
        by_token = {f["token"]: f for f in report["findings"]}
        for token in ("Bingbot", "meta-externalagent",
                      "meta-webindexer", "meta-externalfetcher"):
            self.assertEqual(by_token[token]["evidence_label"],
                             DIRECT, token)

    def test_every_row_carries_obedience_and_crawl_delay(self):
        self.assertEqual(len(robots.CRAWLER_TABLE), 25)
        for row in robots.CRAWLER_TABLE:
            self.assertIn("obedience_statement", row, row["token"])
            self.assertIsInstance(row["obedience_statement"], str)
            self.assertTrue(row["obedience_statement"].strip(),
                            row["token"])
            self.assertIn("crawl_delay_position", row, row["token"])
            self.assertIn(
                row["crawl_delay_position"],
                ("supported", "ignored", "not documented"),
                row["token"])

    def test_documented_crawl_delay_positions(self):
        rows = self.rows_by_number()
        self.assertEqual(rows[4]["crawl_delay_position"], "supported")
        self.assertEqual(rows[7]["crawl_delay_position"], "ignored")
        self.assertEqual(rows[15]["crawl_delay_position"], "ignored")
        self.assertEqual(rows[24]["crawl_delay_position"], "supported")
        self.assertEqual(rows[25]["crawl_delay_position"], "supported")


class TestD15HeadingOffsets(unittest.TestCase):
    """D-15: Markdown heading entries stand in extracted text
    coordinates, as HTML heading entries already do."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = str(Path(self.tmp.name) / "home")
        Path(self.home).mkdir()

    def test_w7_fixture_heading_offset_is_text_offset(self):
        result = acquisition.extract_page(
            self.home, product_id="p-example", page_path=str(PAGE),
            audit_date=AUDIT_DATE)
        extracted = result["extracted"]
        text = extracted["running_text"]
        headings = extracted["headings"]
        self.assertEqual(headings[1]["text"], "Evidence")
        self.assertEqual(headings[1]["start"], 83)
        self.assertEqual(
            text[headings[1]["start"]:
                 headings[1]["start"] + len("Evidence")], "Evidence")
        sections = extracted["sections"]
        self.assertEqual(sections[1]["start"], 83)

    def test_markdown_and_html_heading_offsets_agree(self):
        md_path = Path(self.tmp.name) / "pair.md"
        md_path.write_text(
            "# First Head\n\nBody one text.\n\n## Second Head\n\n"
            "Body two text.\n", encoding="utf-8")
        html_path = Path(self.tmp.name) / "pair.html"
        html_path.write_text(
            "<h1>First Head</h1><p>Body one text.</p>"
            "<h2>Second Head</h2><p>Body two text.</p>",
            encoding="utf-8")
        md = acquisition.extract_page(
            self.home, product_id="p-example", page_path=str(md_path),
            audit_date=AUDIT_DATE)["extracted"]
        html = acquisition.extract_page(
            self.home, product_id="p-example",
            page_path=str(html_path), audit_date=AUDIT_DATE)["extracted"]
        self.assertEqual(md["running_text"], html["running_text"])
        self.assertEqual(
            [h["start"] for h in md["headings"]],
            [h["start"] for h in html["headings"]])
        for extracted in (md, html):
            for heading in extracted["headings"]:
                start = heading["start"]
                self.assertEqual(
                    extracted["running_text"][start:start + len(
                        heading["text"])], heading["text"])


class TestD29StandingAuditForm(F7Base):
    """D-29: a form request on a standing audit renders the stored
    record and appends no new audit; a fresh audit call still
    creates a new run."""

    def entry_count(self):
        return service.status(home=str(self.home))["entry_count"]

    def test_cli_second_form_renders_stored_record(self):
        code, advanced = cli(
            ["audit", "--home", str(self.home),
             "--page_file", str(PAGE), "--audit_date", AUDIT_DATE,
             "--form", "advanced"])
        self.assertEqual(code, 0)
        run_id = json.loads(advanced)["run_id"]
        before = self.entry_count()
        code, agentic = cli(
            ["audit", "--home", str(self.home),
             "--run_id", run_id, "--form", "agentic"])
        self.assertEqual(code, 0)
        self.assertEqual(self.entry_count(), before)
        parsed = json.loads(agentic)
        self.assertEqual(parsed["report"]["run_id"], run_id)
        self.assertIn("schema_stamp", parsed)

    def test_service_second_form_renders_stored_record(self):
        """Supersession recorded (Step 16 supplementary wave,
        defect E-05, on the F3 pattern): as first written this
        test named the page file and the audit date beside the
        run identity in the second form call, which is the
        defective form E-05 cures: a call naming run_id with
        any fresh audit input beside it now refuses
        MALFORMED_CALL at row U-8. The second form call here
        now names the run identity alone. Its name, intent,
        and assertions stand unchanged: a form request on a
        standing audit renders the stored record and appends
        nothing."""
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        before = self.entry_count()
        again = service.audit(
            home=str(self.home),
            run_id=record["run_id"])
        self.assertEqual(self.entry_count(), before)
        self.assertEqual(again["run_id"], record["run_id"])
        self.assertEqual(again["checks"], record["checks"])
        self.assertEqual(again["score"], record["score"])

    def test_fresh_audit_still_creates_a_new_run(self):
        first = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        before = self.entry_count()
        second = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.assertGreater(self.entry_count(), before)
        self.assertNotEqual(second["run_id"], first["run_id"])


if __name__ == "__main__":
    unittest.main()
