"""Step 16 fix F6 tests: checks and scoring defects D-11, D-12,
D-24, and D-25.

Written test first against the round 1 audit papers for slice
S3 (A4) and the Blue seat (A14), and the brief passages they
cite: Section 5.7 earning rules for statistics and citations,
the Section 5.7 score formula, and the IM7-BRK-3 landing in
Section 5.8 for the secondary figure on the not applicable
as zero basis.
"""

import unittest

from citeline import checks
from citeline import journal


def secondary_value(score):
    figure = field(score, "secondary_figure")
    if figure is None:
        return None
    return field(figure, "value")


def field(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def make_page(paragraphs=None, raw_text=None, sentences=None, links=(),
              word_count=None):
    if raw_text is not None:
        running_text = raw_text
        flat = list(sentences or [])
    else:
        paras = [list(p) for p in (paragraphs or [])]
        flat = [s for p in paras for s in p]
        running_text = "\n\n".join(" ".join(p) for p in paras)
    if word_count is None:
        word_count = len(running_text.split())
    return {
        "running_text": running_text,
        "sentences": flat,
        "paragraphs": [],
        "headings": [],
        "sections": [{
            "heading_text": None,
            "start": 0,
            "end": len(running_text),
            "references_section": False,
        }],
        "links": list(links),
        "blockquotes": [],
        "lists": [],
        "tables": [],
        "date_strings": [],
        "canonical_link_element": None,
        "meta_robots": None,
        "word_count": word_count,
        "extracted_text_length": len(running_text),
        "extraction_notes": [],
    }


def make_facts(**overrides):
    facts = {
        "product_name": "Macroforge",
        "aliases": ["Macroforge"],
        "category_terms": ["workbench"],
        "canonical_line": "Macroforge is a campaign workbench for agent teams.",
        "is_product_page": True,
        "domain": "macroforge.example",
        "competitors": [{"name": "Rivalforge", "aliases": ["Rivalforge"]}],
    }
    facts.update(overrides)
    return facts


def run(page, facts=None):
    results = checks.run_checks(
        page, facts or make_facts(), audit_date="2026-11-14")
    return {field(r, "check_id"): r for r in results}


def result(check_id, weight, earned, status=None, detail_counts=None):
    return {
        "check_id": check_id,
        "weight": weight,
        "earned": earned,
        "status": status,
        "reason_code": "TEST",
        "evidence_class": "paper_tested",
        "evidence_spans": [],
        "section_breakdown": [],
        "detail_counts": detail_counts or {},
        "lexicon_coverage": None,
    }


def stored_run_results(numerator_checks, na_checks, evidence_counts=None):
    """CheckResult dicts in registry order from (earned) pairs.

    numerator_checks and na_checks map check_id to earned; the
    weights are the registry weights of brief Section 5.7.
    evidence_counts carries the stored per check counts the
    evidence cap reads (distinct targets, statistic tokens,
    attributed spans) for the three evidence checks.
    """
    weights = {
        "answer_first": 12, "citations": 16, "statistics": 13,
        "quotations": 11, "comparison": 10, "freshness": 8,
        "description_consistency": 8, "keyword_stuffing": 8,
        "fluff": 7, "unproven_superlatives": 7,
    }
    count_keys = {
        "citations": "distinct_target_count",
        "statistics": "statistic_token_count",
        "quotations": "attributed_span_count",
    }
    out = []
    for check_id, weight in weights.items():
        counts = {}
        if evidence_counts and check_id in count_keys:
            counts = {count_keys[check_id]: evidence_counts[check_id]}
        if check_id in na_checks:
            out.append(result(check_id, weight, na_checks[check_id],
                              status="not_applicable",
                              detail_counts=counts))
        else:
            out.append(result(check_id, weight,
                              numerator_checks[check_id],
                              detail_counts=counts))
    return out


class TestD11YearAloneWithComma(unittest.TestCase):
    def test_year_alone_followed_by_comma_counts_zero(self):
        page = make_page(paragraphs=[
            ["Trials in 2025, ran well today for the whole team."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "detail_counts")["statistic_token_count"], 0)
        self.assertEqual(field(r, "earned"), 0.0)

    def test_year_alone_other_punctuation_counts_zero(self):
        for sentence in (
            "Trials in 2025 ran well today for the whole team.",
            "Trials in 2025. Ran well today for the whole team.",
        ):
            page = make_page(paragraphs=[[sentence]])
            r = run(page)["statistics"]
            self.assertEqual(
                field(r, "detail_counts")["statistic_token_count"], 0,
                sentence)

    def test_genuine_tokens_beside_a_comma_year_still_count(self):
        page = make_page(paragraphs=[[
            "Testing in 2025, recorded 1,200 cases and 42 percent gains."
        ]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "detail_counts")["statistic_token_count"], 2)
        self.assertEqual(field(r, "earned"), 0.5)
        excerpts = [s["excerpt"] for s in field(r, "evidence_spans")]
        self.assertEqual(excerpts, ["1,200", "42 percent"])

    def test_thousands_token_before_sentence_comma_keeps_clean_span(self):
        page = make_page(paragraphs=[[
            "The count reached 1,200, and then grew again today."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "detail_counts")["statistic_token_count"], 1)
        excerpts = [s["excerpt"] for s in field(r, "evidence_spans")]
        self.assertEqual(excerpts, ["1,200"])

    def test_year_with_multiplier_word_is_not_standing_alone(self):
        page = make_page(paragraphs=[[
            "Revenue reached 2025 million across the whole region today."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "detail_counts")["statistic_token_count"], 1)


class TestD12CoverageOverParagraphOccurrences(unittest.TestCase):
    LONG_ONE = ("Alpha bravo charlie delta echo foxtrot golf hotel "
                "india https://example.net/data juliet kilo.")
    LONG_TWO = ("Lima mike november oscar papa quebec romeo sierra "
                "tango https://example.net/data uniform victor.")
    LONG_PLAIN = ("Whiskey xray yankee zulu alpha bravo charlie delta "
                  "echo foxtrot golf hotel india juliet.")

    def test_same_target_in_two_paragraphs_credits_both(self):
        page = make_page(paragraphs=[[self.LONG_ONE], [self.LONG_TWO]])
        r = run(page)["citations"]
        self.assertEqual(field(r, "detail_counts")["distinct_target_count"], 1)
        # Coverage 1.0: both long sentences sit in a paragraph
        # holding the counted target. Count component 1/3.
        # Earned is 0.5 times 1/3 plus 0.5 times 1.0, at 0.667.
        self.assertEqual(field(r, "earned"), 0.667)

    def test_same_target_in_one_paragraph_only_control(self):
        page = make_page(paragraphs=[[self.LONG_ONE], [self.LONG_PLAIN]])
        r = run(page)["citations"]
        self.assertEqual(field(r, "detail_counts")["distinct_target_count"], 1)
        # Coverage 0.5: one of two long sentences sits in a
        # citation holding paragraph. Earned 0.417.
        self.assertEqual(field(r, "earned"), 0.417)

    def test_same_target_as_links_in_two_paragraphs_credits_both(self):
        first = ("Alpha bravo charlie delta echo foxtrot golf hotel "
                 "india source juliet kilo.")
        second = ("Lima mike november oscar papa quebec romeo sierra "
                  "tango source uniform victor.")
        text = first + "\n\n" + second
        links = [
            {"text": "source", "target": "https://example.net/data",
             "start": text.index("source"),
             "end": text.index("source") + len("source")},
            {"text": "source", "target": "https://example.net/data",
             "start": text.rindex("source"),
             "end": text.rindex("source") + len("source")},
        ]
        page = make_page(raw_text=text, sentences=[first, second],
                         links=links)
        r = run(page)["citations"]
        self.assertEqual(field(r, "detail_counts")["distinct_target_count"], 1)
        self.assertEqual(field(r, "earned"), 0.667)


class TestD24SecondaryFigure(unittest.TestCase):
    def test_run_9_and_25_basis_secondary_figure(self):
        # Stored session runs 9, 25, and 29 share this shape:
        # applicable earned times weight sums to 26.45, with
        # description_consistency not applicable on run 25 and
        # comparison also not applicable on run 9. The figure
        # on the total weight of 100 is 26.45 rounded to one
        # decimal place, 26.5.
        checks_25 = {
            "answer_first": 0.6, "citations": 0.0, "statistics": 0.25,
            "quotations": 0.0, "comparison": 0.0, "freshness": 0.0,
            "keyword_stuffing": 0.25, "fluff": 1.0,
            "unproven_superlatives": 1.0,
        }
        score = checks.compute_score(stored_run_results(
            checks_25, {"description_consistency": 1.0},
            evidence_counts={"citations": 0, "statistics": 1,
                             "quotations": 0}))
        self.assertEqual(secondary_value(score), 26.5)

    def test_run_11_basis_secondary_figure(self):
        # Stored session run 11: applicable earned times weight
        # sums to 50.722, comparison and description_consistency
        # not applicable. The figure is 50.722 rounded to one
        # decimal place, 50.7.
        applicable = {
            "answer_first": 0.6, "citations": 0.267, "statistics": 0.75,
            "quotations": 0.5, "freshness": 1.0,
            "keyword_stuffing": 0.25, "fluff": 1.0,
            "unproven_superlatives": 1.0,
        }
        score = checks.compute_score(stored_run_results(
            applicable,
            {"comparison": 0.6, "description_consistency": 0.3},
            evidence_counts={"citations": 1, "statistics": 3,
                             "quotations": 1}))
        self.assertEqual(secondary_value(score), 50.7)

    def test_fully_applicable_page_prints_no_secondary_figure(self):
        applicable = {
            "answer_first": 1.0, "citations": 1.0, "statistics": 0.5,
            "quotations": 0.5, "comparison": 0.6, "freshness": 1.0,
            "description_consistency": 1.0, "keyword_stuffing": 1.0,
            "fluff": 1.0, "unproven_superlatives": 1.0,
        }
        score = checks.compute_score(stored_run_results(
            applicable, {},
            evidence_counts={"citations": 1, "statistics": 1,
                             "quotations": 1}))
        self.assertIsNone(field(score, "secondary_figure"))

    def test_all_not_applicable_suppresses_secondary_figure(self):
        na = {
            "answer_first": 0.0, "citations": 0.0, "statistics": 0.0,
            "quotations": 0.0, "comparison": 0.0, "freshness": 0.0,
            "description_consistency": 0.0, "keyword_stuffing": 0.0,
            "fluff": 0.0, "unproven_superlatives": 0.0,
        }
        results = stored_run_results({}, na)
        score = checks.compute_score(results)
        self.assertIsNone(field(score, "value"))
        self.assertIsNone(field(score, "secondary_figure"))

    def test_secondary_figure_carries_the_evidence_cap(self):
        # The cap trigger stands on counts, not earned values:
        # the three evidence counts stand at zero while the
        # applicable earned sum is high, and one check stands
        # not applicable, so the secondary figure caps at 39
        # on the same trigger as the headline score.
        results = [
            result("answer_first", 12, 1.0),
            result("citations", 16, 1.0,
                   detail_counts={"distinct_target_count": 0}),
            result("statistics", 13, 1.0,
                   detail_counts={"statistic_token_count": 0}),
            result("quotations", 11, 1.0,
                   detail_counts={"attributed_span_count": 0}),
            result("comparison", 10, 1.0),
            result("freshness", 8, 1.0),
            result("description_consistency", 8, 1.0,
                   status="not_applicable"),
            result("keyword_stuffing", 8, 1.0),
            result("fluff", 7, 1.0),
            result("unproven_superlatives", 7, 1.0),
        ]
        score = checks.compute_score(results)
        self.assertTrue(field(score, "cap_status"))
        self.assertEqual(field(score, "value"), 39.0)
        self.assertEqual(secondary_value(score), 39.0)


    def test_secondary_figure_stands_in_journal_canonical_form(self):
        # The ScoreObject travels inside the audit record in
        # the journal, whose canonical form renders a non
        # integer number only under a member whose scale
        # stands defined. The figure under the member named
        # value carries the score scale, so an audit record
        # holding the figure renders without error, where a
        # bare figure under a new member name cannot stand.
        applicable = {
            "answer_first": 0.6, "citations": 0.0, "statistics": 0.25,
            "quotations": 0.0, "comparison": 0.0, "freshness": 0.0,
            "keyword_stuffing": 0.25, "fluff": 1.0,
            "unproven_superlatives": 1.0,
        }
        score = checks.compute_score(stored_run_results(
            applicable, {"description_consistency": 1.0},
            evidence_counts={"citations": 0, "statistics": 1,
                             "quotations": 0}))
        entry = {"entry_kind": "audit_record",
                 "payload": {"score": score}}
        rendered = journal.canonical_bytes(entry)
        self.assertIn(b'"secondary_figure"', rendered)
        self.assertIn(b'"value":26.5', rendered)


class TestD25ExactRounding(unittest.TestCase):
    def test_runs_25_and_29_recompute_to_28_8(self):
        # Stored session runs 25 and 29: numerator 26.45 over
        # applicable weight 92 is exactly 28.75, which rounds
        # to 28.8 at one decimal place, not 28.7.
        applicable = {
            "answer_first": 0.6, "citations": 0.0, "statistics": 0.25,
            "quotations": 0.0, "comparison": 0.0, "freshness": 0.0,
            "keyword_stuffing": 0.25, "fluff": 1.0,
            "unproven_superlatives": 1.0,
        }
        score = checks.compute_score(stored_run_results(
            applicable, {"description_consistency": 1.0},
            evidence_counts={"citations": 0, "statistics": 1,
                             "quotations": 0}))
        self.assertEqual(field(score, "value"), 28.8)
        self.assertEqual(field(score, "band"), "poor")


W6_SENTENCES = [
    "Example Product answers questions with citations.",
    ("Example Product is a citation software tool that answers "
     "questions with citations, and it does so in the first "
     "sentences of this page."),
    ("Independent testing recorded 42 percent faster retrieval "
     "across 1,200 trials in 2025, according to the study at "
     "https://example.org/study and the data at "
     "https://example.net/data."),
    ('"The retrieval was measurably faster," said Dr. Lee of '
     "the testing group, describing the results at "
     "https://example.org/study."),
    ("Compared with Rival, Example Product answers questions "
     "with citations in fewer steps, and the comparison table "
     "stands at https://example.net/data."),
    ("This page was updated on 2026-11-01 and states its "
     "sources beside each figure."),
]


def w6_page():
    paragraphs = [[s] for s in W6_SENTENCES]
    return make_page(paragraphs=paragraphs)


def w6_facts():
    return make_facts(
        product_name="Example Product",
        aliases=["Example Product"],
        category_terms=[],
        canonical_line=(
            "Example Product is a tool that answers questions "
            "with citations."),
        is_product_page=False,
        domain="example.org",
        competitors=[{"name": "Rival", "aliases": ["Rival"]}],
    )


class TestW6SessionMaterialCorrected(unittest.TestCase):
    def test_w6_statistics_corrected(self):
        r = run(w6_page(), w6_facts())["statistics"]
        self.assertEqual(field(r, "detail_counts")["statistic_token_count"], 2)
        self.assertEqual(field(r, "earned"), 0.5)

    def test_w6_citations_corrected(self):
        r = run(w6_page(), w6_facts())["citations"]
        self.assertEqual(field(r, "detail_counts")["distinct_target_count"], 1)
        self.assertEqual(field(r, "earned"), 0.367)

    def test_w6_score_corrected_on_both_limbs(self):
        results = checks.run_checks(
            w6_page(), w6_facts(), audit_date="2026-11-14")
        score = checks.compute_score(results)
        self.assertEqual(field(score, "value"), 59.8)
        self.assertEqual(field(score, "band"), "thin")
        # Corrected applicable numerator 49.072 on the total
        # weight of 100 gives the secondary figure 49.1.
        self.assertEqual(secondary_value(score), 49.1)


if __name__ == "__main__":
    unittest.main()
