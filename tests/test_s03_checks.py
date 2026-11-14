"""Slice S3 page checks and scoring tests, Step 13, Citeline.

Written before the product exists. Every test imports the
product package citeline and calls the checks module under
the name the plan states (plan Part A slice S3, module
checks, owning CheckResult and the ScoreObject computation).
Import or attribute failure is the expected red state
(R-20). No stub and no mock of the product stands in this
file. Dates are call inputs, never clock reads (plan
Section 1.5 date handling).

Row naming: every test method docstring names the matrix
row it pins by section qualified identifier (plan Section
1.3 entry S3, by seam) and the oracle passage. Rows the
plan leaves open stand in design/tests/blocked-w3.md, not
here. CRAWL_THIN stands withdrawn as an audit output and
no test in this file names it.
"""

import json
import os
import time
import unittest

from citeline import checks
from citeline import errors

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
AUDIT_DATE = "2026-11-14"

HONESTY_SENTENCE = (
    "This score is a signal index. It measures the presence of "
    "citability signals. It is not validated as a predictor of "
    "citation, and it does not verify truth."
)


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def make_page(paragraphs=None, raw_text=None, sentences=None, links=(),
              headings=(), sections=None, lists=(), tables=(),
              blockquotes=(), word_count=None):
    """Build an ExtractedPage input in the plan Section 5.1 field form.

    paragraphs is a list of paragraphs, each a list of sentence
    strings. The segmentation fields are supplied as inputs here,
    because ExtractedPage carries them as fields; no expectation
    in this file is computed by this helper.
    """
    if raw_text is not None:
        running_text = raw_text
        flat = list(sentences or [])
        paras = [[s] for s in flat]
    else:
        paras = [list(p) for p in (paragraphs or [])]
        flat = [s for p in paras for s in p]
        running_text = "\n\n".join(" ".join(p) for p in paras)
    if word_count is None:
        word_count = sum(len(s.split()) for s in flat)
    if sections is None:
        sections = [{
            "heading_text": None,
            "start": 0,
            "end": len(running_text),
            "references_section": False,
        }]
    return {
        "running_text": running_text,
        "sentences": flat,
        "paragraphs": [" ".join(p) for p in paras],
        "headings": list(headings),
        "sections": sections,
        "links": list(links),
        "blockquotes": list(blockquotes),
        "lists": list(lists),
        "tables": list(tables),
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


def link(target, text, start):
    return {"text": text, "target": target, "start": start, "end": start + len(text)}


def run(page, facts=None):
    results = checks.run_checks(page, facts or make_facts(), audit_date=AUDIT_DATE)
    return {field(r, "check_id"): r for r in results}


def filler_sentences(count, words_per=10):
    """Distinct filler sentences of exactly words_per words each.

    Input construction only: the sentences hold no statistic
    token, no date, no quotation, no superlative, and no
    registry term, by construction of the word bank.
    """
    bank = ["alpha", "bravo", "charlie", "delta", "echo",
            "foxtrot", "golf", "hotel", "india"]
    out = []
    for i in range(count):
        words = ["Filler%02d" % i] + [bank[(i + j) % len(bank)]
                                      for j in range(words_per - 1)]
        out.append(" ".join(words) + ".")
    return out


# The shared scored page (fixture w3-page-score-a.txt carries the
# same running text). Hand computed expectations, from brief
# Section 5.7 earning rules applied by hand:
#   answer_first 1.0, citations 1.0, statistics 0.5,
#   quotations 0.5, comparison 0.6, freshness 1.0,
#   description_consistency 1.0, keyword_stuffing 1.0,
#   fluff 1.0, unproven_superlatives 1.0.
SCORE_A_SENTENCES = [
    "Macroforge is a campaign workbench for agent teams.",
    "See https://example.org/a and https://example.org/b and https://example.org/c for details.",
    "Adoption reached 42% across 10 regions.",
    '"Teams plan better together" said Priya Nair.',
    "Versus Rivalforge for planning work.",
    "Updated: 2026-08-16",
]


def score_a_page():
    paragraphs = [[s] for s in SCORE_A_SENTENCES]
    running = "\n\n".join(SCORE_A_SENTENCES)
    links = []
    for target in ("https://example.org/a", "https://example.org/b",
                   "https://example.org/c"):
        links.append(link(target, target, running.index(target)))
    return make_page(paragraphs=paragraphs, links=links)


class TestCheckRegistryFacts(unittest.TestCase):
    def test_ten_checks_ids_weights_evidence_classes(self):
        """Plan Section 1.3 S3 limb (a) and plan Section 5.1 CheckResult. Oracle: brief Section 5.7 head, the ten checks with weights and basis adopted there (answer_first 12 tool defined, citations 16 paper tested, statistics 13 paper tested, quotations 11 paper tested, comparison 10 post asserted, freshness 8 post asserted, description_consistency 8 post asserted, keyword_stuffing 8 inverted paper tested, fluff 7 inverted post asserted, unproven_superlatives 7 inverted tool defined; weights sum to 100), and brief Section 5.4 check 1 identifier list for the check ids in order."""
        results = checks.run_checks(score_a_page(), make_facts(), audit_date=AUDIT_DATE)
        got = [(field(r, "check_id"), field(r, "weight"), field(r, "evidence_class"))
               for r in results]
        expected = [
            ("answer_first", 12, "tool_defined"),
            ("citations", 16, "paper_tested"),
            ("statistics", 13, "paper_tested"),
            ("quotations", 11, "paper_tested"),
            ("comparison", 10, "post_asserted"),
            ("freshness", 8, "post_asserted"),
            ("description_consistency", 8, "post_asserted"),
            ("keyword_stuffing", 8, "paper_tested"),
            ("fluff", 7, "post_asserted"),
            ("unproven_superlatives", 7, "tool_defined"),
        ]
        self.assertEqual(got, expected)
        self.assertEqual(sum(w for _, w, _ in expected), 100)

    def test_status_value_set_pins_as_data(self):
        """Plan Section 1.3 S3 limb (b), SEAM-STATUS at the CheckResult status field only. Oracle: plan Section 5.1 CheckResult, status one of pass, warn, fail, not_applicable; the value set is brief data and pins as data, and no derivation from earned values is asserted anywhere in this file."""
        self.assertEqual(set(checks.STATUS_VALUES),
                         {"pass", "warn", "fail", "not_applicable"})
        self.assertEqual(len(checks.STATUS_VALUES), 4)


class TestAnswerFirst(unittest.TestCase):
    def test_window_alias_and_category_declarative_full(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7 answer first earning rule, earned 1.0 where the window (first 2 sentences or first 60 words, whichever ends later) holds a product alias and a category term and is declarative; reason code AF_FULL from the Section 5.7 reason code list."""
        results = run(score_a_page())
        r = results["answer_first"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "AF_FULL")

    def test_alias_only_partial(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7, 0.6 for an alias only in a declarative window; reason code AF_PARTIAL."""
        page = make_page(paragraphs=[["Macroforge leads the planning session."]])
        r = run(page)["answer_first"]
        self.assertEqual(field(r, "earned"), 0.6)
        self.assertEqual(field(r, "reason_code"), "AF_PARTIAL")

    def test_category_only_partial(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7, 0.4 for a category term only in a declarative window; reason code AF_PARTIAL."""
        page = make_page(paragraphs=[["The workbench leads the planning session."]])
        r = run(page)["answer_first"]
        self.assertEqual(field(r, "earned"), 0.4)
        self.assertEqual(field(r, "reason_code"), "AF_PARTIAL")

    def test_question_mark_gates_every_limb(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7, the no question mark condition gates the 0.6 and 0.4 limbs as well as the 1.0 limb; a window holding a question mark earns 0 under every limb; reason code AF_TERM_NOT_DECLARATIVE."""
        page = make_page(paragraphs=[["Is Macroforge a workbench for teams?"]])
        r = run(page)["answer_first"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "AF_TERM_NOT_DECLARATIVE")

    def test_term_outside_window(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7 window rule; the first two sentences here hold 31 words each, so the window ends at 62 words, and the alias first stands in the third sentence, outside the window; reason code AF_OUTSIDE_WINDOW."""
        s1 = ("The guide explains how teams plan weekly work and review "
              "outcomes with care and calm attention to detail across "
              "every project they run together in shared sessions each "
              "week without fail.")
        s2 = ("The handbook describes how groups prepare monthly reviews "
              "and record decisions with care and calm attention to "
              "detail across every project they run together in shared "
              "sessions each week without fail.")
        self.assertEqual(len(s1.split()), 31)
        self.assertEqual(len(s2.split()), 31)
        page = make_page(paragraphs=[[s1, s2],
                                     ["Macroforge appears here at last."]])
        r = run(page)["answer_first"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "AF_OUTSIDE_WINDOW")

    def test_no_term_anywhere(self):
        """Plan Section 1.3 S3 limb (a), check answer_first. Oracle: brief Section 5.7, earned 0 where no alias and no category term stands anywhere on the page; reason code AF_MISSING_TERM."""
        page = make_page(paragraphs=[["The session covers planning and review."]])
        r = run(page)["answer_first"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "AF_MISSING_TERM")


class TestCitations(unittest.TestCase):
    def test_three_targets_full_coverage_fallback(self):
        """Plan Section 1.3 S3 limb (a), check citations. Oracle: brief Section 5.7 citations rule, count component min(count, 3) divided by 3, and where no sentence is longer than 8 words the coverage component is 1 where the citation count is at least 1; the two components blend equally; reason code CIT_COUNT."""
        r = run(score_a_page())["citations"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "CIT_COUNT")

    def test_evidence_spans_match_supplied_text(self):
        """Plan Section 1.3 S3 limb (a), evidence spans. Oracle: plan Section 5.1 CheckResult evidence_spans (start, end, excerpt), and brief Section 5.5 Advanced conformance span check, each excerpt matches the supplied text at its stated offsets."""
        page = score_a_page()
        r = run(page)["citations"]
        spans = field(r, "evidence_spans")
        self.assertEqual(len(spans), 3)
        text = page["running_text"]
        excerpts = set()
        for span in spans:
            start, end = field(span, "start"), field(span, "end")
            self.assertEqual(text[start:end], field(span, "excerpt"))
            excerpts.add(field(span, "excerpt"))
        self.assertEqual(excerpts, {"https://example.org/a",
                                    "https://example.org/b",
                                    "https://example.org/c"})

    def test_partial_count_and_coverage_rounding(self):
        """Plan Section 1.3 S3 limb (a), check citations. Oracle: brief Section 5.7 citations rule applied by hand: one distinct target gives a count component of 1/3; two sentences longer than 8 words, one in the citation holding paragraph, give coverage 0.5; earned is 0.5 times 1/3 plus 0.5 times 0.5, which is 0.417 at the CheckResult rounding of 3 decimals (plan Section 5.1)."""
        long_a = "The full guide explains every planning step in careful detail today."
        long_b = "The second chapter explains every review step in careful detail today."
        running = long_a + "\n\n" + long_b
        links = [link("https://example.org/a", "https://example.org/a", -1)]
        # The link text stands inside the first paragraph as its own
        # sentence fragment position: place the target text at the
        # end of the first paragraph.
        para_a = long_a + " https://example.org/a"
        running = para_a + "\n\n" + long_b
        links = [link("https://example.org/a", "https://example.org/a",
                      running.index("https://example.org/a"))]
        page = make_page(raw_text=running, sentences=[para_a, long_b],
                         links=links, word_count=len(running.split()))
        r = run(page)["citations"]
        self.assertEqual(field(r, "earned"), 0.417)
        self.assertEqual(field(r, "reason_code"), "CIT_COUNT")

    def test_no_targets(self):
        """Plan Section 1.3 S3 limb (a), check citations. Oracle: brief Section 5.7, no citation targets earns 0; reason code CIT_NO_TARGETS, the Section 10.9 code the reason code passage states for a fixture with no qualifying target."""
        page = make_page(paragraphs=[["The session covers planning and review."]])
        r = run(page)["citations"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "CIT_NO_TARGETS")

    def test_internal_and_anchor_links_excluded(self):
        """Plan Section 1.3 S3 limb (a), check citations. Oracle: brief Section 5.7, distinct citation targets are counted with internal and self links excluded; a page holding only an anchor link and a relative link holds no counted target."""
        running = "Read the notes first. See the index next."
        links = [link("#top", "#top", 0), link("/docs", "/docs", 5)]
        page = make_page(raw_text=running,
                         sentences=["Read the notes first.", "See the index next."],
                         links=links, word_count=8)
        r = run(page)["citations"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "CIT_NO_TARGETS")

    def test_self_only_specificity_rule(self):
        """Plan Section 1.3 S3 limb (a), check citations, reason code assignment. Oracle: brief Section 5.7 field mapping specificity rule, acceptance condition C2 at Section 10.9 names the exact case of a fixture whose targets are all self citations, so that case carries CIT_SELF_ONLY and not CIT_NO_TARGETS, even though no qualifying target stands in it."""
        running = "Our own overview stands at https://macroforge.example/about for readers."
        links = [link("https://macroforge.example/about",
                      "https://macroforge.example/about",
                      running.index("https://macroforge.example/about"))]
        page = make_page(raw_text=running, sentences=[running], links=links,
                         word_count=len(running.split()))
        r = run(page)["citations"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "CIT_SELF_ONLY")

    def test_duplicate_target_counts_once(self):
        """Plan Section 1.3 S3 limb (a), check citations. Oracle: brief Section 5.7, distinct citation targets are counted; the same target twice is one distinct target, giving a count component of 1/3, and the one long sentence sits in the citation holding paragraph, giving coverage 1, so earned is 0.667 at 3 decimals."""
        sentence = ("The full guide explains every planning step in careful "
                    "detail today with https://example.org/a and again "
                    "https://example.org/a inside.")
        links = [link("https://example.org/a", "https://example.org/a",
                      sentence.index("https://example.org/a")),
                 link("https://example.org/a", "https://example.org/a",
                      sentence.rindex("https://example.org/a"))]
        page = make_page(paragraphs=[[sentence]], links=links)
        r = run(page)["citations"]
        self.assertEqual(field(r, "earned"), 0.667)
        self.assertEqual(field(r, "reason_code"), "CIT_COUNT")


class TestStatistics(unittest.TestCase):
    def test_four_tokens_full(self):
        """Plan Section 1.3 S3 limb (a), check statistics. Oracle: brief Section 5.7 statistics rule, earned is min(count, 4) divided by 4; the sentence holds four statistic tokens under the counting unit (42% with its sign, $19 with its symbol, the decimal 3.5, and the ratio 10:1, each one maximal figure counted once); reason code STAT_COUNT."""
        page = make_page(paragraphs=[["Adoption reached 42% and $19 with 3.5 and 10:1 overall."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "STAT_COUNT")
        excerpts = {field(s, "excerpt") for s in field(r, "evidence_spans")}
        self.assertEqual(excerpts, {"42%", "$19", "3.5", "10:1"})

    def test_excluded_forms_count_nothing(self):
        """Plan Section 1.3 S3 limb (a), check statistics. Oracle: brief Section 5.7, the count excludes a year between 1900 and 2099 standing alone, a version string, and a date fragment; reason code STAT_NONE."""
        page = make_page(paragraphs=[["Released in 2026 as version 2.4.1 on 2026-11-12 today."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "STAT_NONE")

    def test_token_inside_quoted_span_excluded(self):
        """Plan Section 1.3 S3 limb (a), check statistics. Oracle: brief Section 5.7, any token inside a quoted span is excluded; the 99% inside the quoted span counts nothing and the 50% outside it counts once, so earned is 0.25."""
        page = make_page(paragraphs=[['"Growth hit 99% last year" the report said.',
                                       "Growth reached 50% this year."]])
        r = run(page)["statistics"]
        self.assertEqual(field(r, "earned"), 0.25)
        self.assertEqual(field(r, "reason_code"), "STAT_COUNT")

    def test_two_tokens_half(self):
        """Plan Section 1.3 S3 limb (a), check statistics. Oracle: brief Section 5.7, min(2, 4) divided by 4 is 0.5, as the scored page case also states."""
        r = run(score_a_page())["statistics"]
        self.assertEqual(field(r, "earned"), 0.5)
        self.assertEqual(field(r, "reason_code"), "STAT_COUNT")


class TestQuotations(unittest.TestCase):
    def test_attributed_by_said_full_formula(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7 quotations rule, quoted spans of at least 4 words are counted, a span is attributed where a cue within 100 characters after the span is present, the cue set closed as said, according to, and a capitalised name; earned is min(attributed plus 0.5 times unattributed, 2) divided by 2, so one attributed span earns 0.5; reason code QUO_COUNT."""
        r = run(score_a_page())["quotations"]
        self.assertEqual(field(r, "earned"), 0.5)
        self.assertEqual(field(r, "reason_code"), "QUO_COUNT")
        spans = field(r, "evidence_spans")
        self.assertEqual(len(spans), 1)
        text = score_a_page()["running_text"]
        span = spans[0]
        self.assertEqual(text[field(span, "start"):field(span, "end")],
                         field(span, "excerpt"))

    def test_attributed_by_capitalised_name(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7, a capitalised name within 100 characters after the span attributes it, so one attributed span earns 0.5."""
        page = make_page(paragraphs=[['"Teams plan better together" Priya Nair wrote in her notes.']])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0.5)
        self.assertEqual(field(r, "reason_code"), "QUO_COUNT")

    def test_unattributed_only(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7, one unattributed span earns min(0.5, 2) divided by 2, which is 0.25, and the reason code passage states a fixture with no attributed span carries QUOTE_NONE_ATTRIBUTED."""
        page = make_page(paragraphs=[['"Teams plan better together" appeared in the notes.']])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0.25)
        self.assertEqual(field(r, "reason_code"), "QUOTE_NONE_ATTRIBUTED")

    def test_mixed_spans_lower_outcome_code_wins(self):
        """Plan Section 1.3 S3 limb (a), reason code assignment. Oracle: brief Section 5.7 quotations rule and field mapping, where the conditions of two codes of one check hold together the field carries the code of the lower earning outcome; one attributed span and one unattributed span earn min(1 plus 0.5, 2) divided by 2, which is 0.75, and the unattributed outcome earns less per span, so the code is QUO_UNATTRIBUTED."""
        page = make_page(paragraphs=[
            ['"Teams plan better together" said Priya Nair.'],
            ['"Groups review outcomes weekly" appeared in the notes.'],
        ])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0.75)
        self.assertEqual(field(r, "reason_code"), "QUO_UNATTRIBUTED")

    def test_short_span_not_counted(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7, quoted spans of at least 4 words are counted; a span of 3 words counts nothing, so earned is 0 and the code is QUOTE_NONE_ATTRIBUTED."""
        page = make_page(paragraphs=[['The note says "plan better together" in passing.']])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "QUOTE_NONE_ATTRIBUTED")

    def test_cue_across_paragraph_boundary_does_not_attribute(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7, the 100 character window is anchored at the end of the span and may not cross a paragraph boundary; the cue in the next paragraph attributes nothing, so the span earns 0.25 unattributed."""
        page = make_page(paragraphs=[
            ['"Teams plan better together" appeared in the notes.'],
            ["Priya said the review followed."],
        ])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0.25)
        self.assertEqual(field(r, "reason_code"), "QUOTE_NONE_ATTRIBUTED")

    def test_cue_beyond_100_characters_does_not_attribute(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check quotations. Oracle: brief Section 5.7, the attribution window is 100 characters after the span; here more than 100 characters of the same paragraph intervene before the cue, so the span earns 0.25 unattributed."""
        filler = " ".join(["ordinary"] * 20) + "."
        self.assertGreater(len(filler), 100)
        page = make_page(paragraphs=[[
            '"Teams plan better together" appeared in the notes.',
            filler,
            "Priya said the review followed.",
        ]])
        r = run(page)["quotations"]
        self.assertEqual(field(r, "earned"), 0.25)
        self.assertEqual(field(r, "reason_code"), "QUOTE_NONE_ATTRIBUTED")


class TestComparison(unittest.TestCase):
    def test_competitor_signal_and_structure(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check comparison. Oracle: brief Section 5.7 comparison rule, four components at weights 0.4, 0.2, 0.2, and 0.2; a competitor name present earns 0.4, a comparison signal from the closed signal list in the rule earns 0.2, and a structured element with at least 3 items in the comparison section earns 0.2; no criterion word stands near the comparison on this page, so the fourth component earns 0 and the total is 0.8; CMP_THIN is the code where the rule earns partial credit."""
        intro = "The page opens with a plain summary of the offering."
        heading = "Comparison"
        body = "Macroforge versus Rivalforge in daily use."
        running = intro + "\n\n" + heading + "\n\n" + body
        sections = [
            {"heading_text": None, "start": 0, "end": len(intro),
             "references_section": False},
            {"heading_text": heading, "start": len(intro) + 2,
             "end": len(running), "references_section": False},
        ]
        lists = [{"items": ["Alpha row", "Beta row", "Gamma row"],
                  "start": running.index(body)}]
        page = make_page(raw_text=running, sentences=[intro, body],
                         headings=[{"text": heading}],
                         sections=sections, lists=lists,
                         word_count=len(running.split()))
        r = run(page)["comparison"]
        self.assertEqual(field(r, "earned"), 0.8)
        self.assertEqual(field(r, "reason_code"), "CMP_THIN")

    def test_competitor_only(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check comparison. Oracle: brief Section 5.7, a competitor name or alias present earns the 0.4 component and nothing else stands on this page, so earned is 0.4 and the code is CMP_THIN."""
        page = make_page(paragraphs=[["Rivalforge appears in the survey of the field."]])
        r = run(page)["comparison"]
        self.assertEqual(field(r, "earned"), 0.4)
        self.assertEqual(field(r, "reason_code"), "CMP_THIN")

    def test_best_for_pattern_is_a_signal(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check comparison. Oracle: brief Section 5.7 comparison signal list, the pattern the token best, then the token for later in the same sentence, is a comparison signal, earning the 0.2 component on its own here."""
        page = make_page(paragraphs=[["The best tool for planning stands here."]])
        r = run(page)["comparison"]
        self.assertEqual(field(r, "earned"), 0.2)
        self.assertEqual(field(r, "reason_code"), "CMP_THIN")

    def test_no_components_missing(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check comparison. Oracle: brief Section 5.7, where neither a comparison heading nor a comparison signal stands, no comparison section stands and the criterion word component earns 0 because it has no section to count from; with no component standing, earned is 0 and the code is CMP_MISSING."""
        page = make_page(paragraphs=[["The session covers planning and review."]])
        r = run(page)["comparison"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "CMP_MISSING")


class TestFreshness(unittest.TestCase):
    """Freshness pins on the 90 day full credit band, stated as a
    Manager settlement under delegation wherever the band is
    stated (plan Section 1.3 S3 freshness limb). No per product
    threshold test stands in this class, because no such
    threshold stands adopted. The audit date is the call input
    2026-11-14 in every case (plan Section 1.5 date handling).
    """

    def fresh(self, lines):
        raw = "\n".join(lines)
        page = make_page(raw_text=raw, sentences=[raw], word_count=len(raw.split()))
        return run(page)["freshness"]

    def test_labelled_date_at_90_days_full_credit(self):
        """Plan Section 1.3 S3 limb (a) and freshness limb, check freshness. Oracle: brief Section 5.7 freshness rule, earned by age in days is 1.0 at 90 or less, on the 90 day full credit band as a Manager settlement under delegation; 2026-08-16 stands 90 days before the audit date input 2026-11-14; FRESH_OK where the rule earns full credit on a date at 90 days or less."""
        r = self.fresh(["Updated: 2026-08-16"])
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FRESH_OK")

    def test_labelled_date_at_91_days(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, earned is 0.7 at 180 or less; 2026-08-15 stands 91 days before the audit date; FRESH_STALE where the rule earns less than full credit on a date beyond the 90 day band."""
        r = self.fresh(["Updated: 2026-08-15"])
        self.assertEqual(field(r, "earned"), 0.7)
        self.assertEqual(field(r, "reason_code"), "FRESH_STALE")

    def test_age_band_edges(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7 age bands applied by hand against the audit date input 2026-11-14: 2026-05-18 is 180 days, earning 0.7; 2026-05-17 is 181 days, earning 0.4; 2025-11-14 is 365 days, earning 0.4; 2025-11-13 is 366 days, earning 0.2; 2024-11-14 is 730 days, earning 0.2; 2024-11-13 is 731 days, earning 0."""
        cases = [
            ("2026-05-18", 0.7), ("2026-05-17", 0.4),
            ("2025-11-14", 0.4), ("2025-11-13", 0.2),
            ("2024-11-14", 0.2), ("2024-11-13", 0),
        ]
        for date, expected in cases:
            with self.subTest(date=date):
                r = self.fresh(["Updated: " + date])
                self.assertEqual(field(r, "earned"), expected)
                self.assertEqual(field(r, "reason_code"), "FRESH_STALE")

    def test_month_name_format(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, the closed format set is an ISO date and Month D, YYYY with the full English month name; August 16, 2026 is the same date as the 90 day case and earns 1.0."""
        r = self.fresh(["Updated: August 16, 2026"])
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FRESH_OK")

    def test_future_date_earns_zero(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, a date after the audit date earns 0; reason code FRESH_FUTURE."""
        r = self.fresh(["Updated: 2026-12-01"])
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FRESH_FUTURE")

    def test_no_date_earns_zero(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, no date earns 0, and no date carries FRESH_NO_DATE alone."""
        r = self.fresh(["The page holds no date at all."])
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FRESH_NO_DATE")

    def test_labelled_limb_beats_earlier_unlabelled_date(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, the rule has two limbs in priority order, labelled lines first; the labelled line governs even where an unlabelled date stands earlier in the text, so the 2026-08-16 labelled date earns 1.0."""
        r = self.fresh(["Released 2020-01-01 for review.",
                        "Updated: 2026-08-16"])
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FRESH_OK")

    def test_first_labelled_line_wins(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, labelled lines are searched in the whole extracted text and the first labelled line in extracted order wins; the first labelled date here is past 730 days, so earned is 0."""
        r = self.fresh(["Updated: 2020-01-01", "Updated: 2026-08-16"])
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FRESH_STALE")

    def test_label_not_at_line_start_falls_to_second_limb(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, a label standing anywhere else in a line makes no labelled line; the date then stands under the second limb, any date in the closed format set in the first 20 lines, and earns on its age, here 1.0."""
        r = self.fresh(["Last reviewed Updated: 2026-08-16 in the log."])
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FRESH_OK")

    def test_second_limb_limited_to_first_20_lines(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, the second limb searches the first 20 lines of the extracted text only; the only date here stands on line 21, so no date is found and the code is FRESH_NO_DATE."""
        lines = ["Line %02d of plain prose." % i for i in range(1, 21)]
        lines.append("Released 2026-08-16 for review.")
        r = self.fresh(lines)
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FRESH_NO_DATE")

    def test_ambiguous_numeric_form_not_parseable(self):
        """Plan Section 1.3 S3 limb (a), check freshness. Oracle: brief Section 5.7, ambiguous numeric forms are expressly not parseable and are never read in either direction; the only date form here is ambiguous, so no date is found."""
        r = self.fresh(["Updated: 11/05/2026"])
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FRESH_NO_DATE")


class TestDescriptionConsistency(unittest.TestCase):
    CANON = "Macroforge is a campaign workbench for agent teams."

    def test_verbatim_present_full(self):
        """Plan Section 1.3 S3 limb (e) in its pinnable precedence limb, check description_consistency. Oracle: brief Section 5.7, full credit only where the canonical line appears verbatim; the sentence here is character for character the canonical line, so no whitespace normalisation question arises; reason code DESC_PRESENT."""
        r = run(score_a_page())["description_consistency"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "DESC_PRESENT")

    def test_verbatim_governs_over_drift(self):
        """Plan Section 1.3 S3 limb (e), rule precedence. Oracle: brief Section 5.7 precedence, verbatim present governs; this page holds both the verbatim canonical line and a drift sentence, and earns 1.0 with DESC_PRESENT."""
        page = make_page(paragraphs=[
            [self.CANON],
            ["Macroforge is the campaign workbench for agent groups."],
        ])
        r = run(page)["description_consistency"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "DESC_PRESENT")

    def test_drift_governs_over_absence(self):
        """Plan Section 1.3 S3 limb (e), rule precedence, exact threshold case. Oracle: brief Section 5.7, where no verbatim line stands, drift governs where a sentence at a Jaccard word similarity of 0.6 or more and not equal to the canonical line stands, earning 0.3; the sentence here is the exact threshold case, sharing 6 distinct words with the canonical line, with 10 distinct words in the union, a similarity of 0.600 computed by hand, which meets the threshold exactly; reason code DESC_DRIFT."""
        page = make_page(paragraphs=[
            ["Macroforge is the campaign workbench for agent groups."],
        ])
        r = run(page)["description_consistency"]
        self.assertEqual(field(r, "earned"), 0.3)
        self.assertEqual(field(r, "reason_code"), "DESC_DRIFT")

    def test_below_similarity_threshold_is_absence(self):
        """Plan Section 1.3 S3 limb (e), check description_consistency. Oracle: brief Section 5.7, absence earns 0 where no sentence stands at 0.6 or more; the sentence here shares 3 of the 10 distinct words in the union with the canonical line, a similarity of 0.3 computed by hand; an absent canonical line carries DESC_MISSING alone."""
        page = make_page(paragraphs=[["Macroforge is built for people."]])
        r = run(page)["description_consistency"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "DESC_MISSING")

    def test_not_applicable_on_non_product_page(self):
        """Plan Section 1.3 S3 limb (a), check description_consistency applicability. Oracle: brief Section 5.7, the check is applicable only on a product page as grill Q20 defines it, recorded by the is_product_page field, and not applicable on any other page; this is an applicability outcome, not a derivation of status from an earned value, and no earned value is asserted for it."""
        page = make_page(paragraphs=[[self.CANON]])
        r = run(page, make_facts(is_product_page=False))["description_consistency"]
        self.assertEqual(field(r, "status"), "not_applicable")


class TestKeywordStuffing(unittest.TestCase):
    def test_low_density_full(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing. Oracle: brief Section 5.7 keyword stuffing rule, density is occurrences times term length in words times 100 divided by word count; on the scored page the product name stands once in 36 words, a density of 2.78, and the category term the same, neither exceeding 3, and no sentence repeats verbatim, so earned is 1.0; reason code STF_OK."""
        r = run(score_a_page())["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "STF_OK")

    def test_density_over_3_loses_half(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing. Oracle: brief Section 5.7, earned starts at 1.0 and loses 0.5 where peak density exceeds 3; here the product name stands 4 times in 100 words, a density of 4, which exceeds 3 and not 5, so earned is 0.5; reason code STF_DENSE."""
        named = ["Macroforge appears in this short line.",
                 "Macroforge appears in that short line.",
                 "Macroforge appears in one short line.",
                 "Macroforge appears in another short line."]
        filler = filler_sentences(7) + ["Filler closing line stands here now."]
        page = make_page(paragraphs=[named + filler])
        self.assertEqual(page["word_count"], 100)
        r = run(page)["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 0.5)
        self.assertEqual(field(r, "reason_code"), "STF_DENSE")

    def test_density_over_5_loses_three_quarters(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing. Oracle: brief Section 5.7, peak density exceeding 5 loses 0.5 and 0.25 more; the product name stands 6 times in 100 words, a density of 6, so earned is 0.25; reason code STF_DENSE."""
        named = ["Macroforge appears in this short line.",
                 "Macroforge appears in that short line.",
                 "Macroforge appears in one short line.",
                 "Macroforge appears in another short line.",
                 "Macroforge appears in a further short line.",
                 "Macroforge appears in the last short line."]
        filler = filler_sentences(6) + ["Filler ends."]
        page = make_page(paragraphs=[named + filler])
        self.assertEqual(page["word_count"], 100)
        r = run(page)["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 0.25)
        self.assertEqual(field(r, "reason_code"), "STF_DENSE")

    def test_multiword_term_density_uses_term_length(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing. Oracle: brief Section 5.7, density multiplies occurrences by the term length in words; the two word category term agent teams stands twice in 100 words, a density of 2 times 2 times 100 divided by 100, which is 4, exceeding 3, so earned is 0.5."""
        facts = make_facts(category_terms=["agent teams"], aliases=[],
                           product_name="Macroforge")
        named = ["The agent teams gathered for the review today.",
                 "The agent teams gathered for the survey today."]
        filler = filler_sentences(8) + ["Filler closing line stands."]
        page = make_page(paragraphs=[named + filler])
        self.assertEqual(page["word_count"], 100)
        r = run(page, facts)["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 0.5)
        self.assertEqual(field(r, "reason_code"), "STF_DENSE")

    def test_verbatim_sentence_repeat_loses_quarter(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing. Oracle: brief Section 5.7, earned loses 0.25 where any sentence repeats verbatim; densities here stand at 1.32 or less, so only the repeat deduction applies and earned is 0.75; reason code STF_REPEAT."""
        repeated = "The weekly review covers open questions."
        named = ["Macroforge helps teams plan.", repeated, repeated]
        filler = filler_sentences(6)
        page = make_page(paragraphs=[named + filler])
        self.assertEqual(page["word_count"], 76)
        r = run(page)["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 0.75)
        self.assertEqual(field(r, "reason_code"), "STF_REPEAT")

    def test_dense_and_repeat_floor_and_code_assignment(self):
        """Plan Section 1.3 S3 limb (a), check keyword_stuffing, reason code assignment. Oracle: brief Section 5.7, the deductions stack and earned is floored at 0 (0.5 over the 5 density line, 0.25 more over it, and 0.25 for a verbatim repeat, against a start of 1.0); the field mapping carries the code of the lower earning outcome, and the density outcome at 0.25 stands lower than the repeat outcome at 0.75, so the code is STF_DENSE."""
        named = ["Macroforge appears in this short line.",
                 "Macroforge appears in that short line.",
                 "Macroforge appears in one short line.",
                 "Macroforge appears in another short line.",
                 "Macroforge appears in a further short line.",
                 "Macroforge appears in the last short line.",
                 "The weekly review covers open questions.",
                 "The weekly review covers open questions."]
        filler = filler_sentences(5)
        page = make_page(paragraphs=[named + filler])
        self.assertEqual(page["word_count"], 100)
        r = run(page)["keyword_stuffing"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "STF_DENSE")


class TestFluff(unittest.TestCase):
    def test_long_page_low_evidence_zero(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check fluff. Oracle: brief Section 5.7 fluff rule, earned is 0 where word count is at least 800 and evidence density (citations plus statistics plus attributed quotes per 100 words) is under 0.5; this page holds 800 words and no evidence, a density of 0; reason code FLF_LONG_LOW_EVIDENCE."""
        page = make_page(paragraphs=[filler_sentences(80)])
        self.assertEqual(page["word_count"], 800)
        r = run(page)["fluff"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "FLF_LONG_LOW_EVIDENCE")

    def test_mid_page_low_evidence(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check fluff. Oracle: brief Section 5.7, earned is 0.4 where word count is 400 to 799 and density is under 0.5; this page holds 500 words and no evidence."""
        page = make_page(paragraphs=[filler_sentences(50)])
        self.assertEqual(page["word_count"], 500)
        r = run(page)["fluff"]
        self.assertEqual(field(r, "earned"), 0.4)
        self.assertEqual(field(r, "reason_code"), "FLF_LONG_LOW_EVIDENCE")

    def test_density_at_half_is_not_under(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check fluff. Oracle: brief Section 5.7, the long page limb needs density under 0.5; four statistic tokens over 800 words give a density of exactly 0.5, which is not under 0.5, and no booster limb is asserted, so earned is 1.0; reason code FLF_OK."""
        stat = "Adoption reached 42% and 50% with 3.5 and 10:1 gains today."
        filler = filler_sentences(78) + ["Filler alpha bravo charlie delta echo foxtrot golf hotel."]
        page = make_page(paragraphs=[filler + [stat]])
        self.assertEqual(page["word_count"], 800)
        r = run(page)["fluff"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FLF_OK")

    def test_short_page_full(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check fluff. Oracle: brief Section 5.7, a page under 400 words stands in the otherwise limb and earns 1.0 where no booster deduction is asserted; the scored page holds 36 words."""
        r = run(score_a_page())["fluff"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "FLF_OK")


class TestUnprovenSuperlatives(unittest.TestCase):
    def test_no_hits_full(self):
        """Plan Section 1.3 S3 limb (c) in its list independent form, check unproven_superlatives. Oracle: brief Section 5.7, earned is 1.0 minus 0.34 per unproven hit, floored at 0; the scored page holds no superlative hit, so earned is 1.0; reason code SUP_OK. No hit case is asserted in this file, because hit behaviour rests on the lexicon and stands blocked at Part B entry B2."""
        r = run(score_a_page())["unproven_superlatives"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "SUP_OK")


class TestScoreComputation(unittest.TestCase):
    def test_scored_page_value_band_and_basis(self):
        """Plan Section 1.3 S3 limb (a), score computation for the non empty case. Oracle: brief Section 5.7 score rule, the sum of earned times weight across applicable checks divided by applicable weight times 100, rounded to one decimal place; the hand computed earned values on the scored page (1.0, 1.0, 0.5, 0.5, 0.6, 1.0, 1.0, 1.0, 1.0, 1.0 against weights 12, 16, 13, 11, 10, 8, 8, 8, 7, 7) sum to 84.0 over an applicable weight of 100, and grill Q9 bands give strong at 80 and over."""
        results = checks.run_checks(score_a_page(), make_facts(), audit_date=AUDIT_DATE)
        score = checks.compute_score(results)
        self.assertEqual(field(score, "value"), 84.0)
        self.assertEqual(field(score, "band"), "strong")
        self.assertFalse(field(score, "cap_status"))
        basis = field(score, "applicable_basis")
        self.assertEqual(field(basis, "applicable_weight"), 100)
        self.assertEqual(set(field(basis, "applicable_checks")),
                         {"answer_first", "citations", "statistics",
                          "quotations", "comparison", "freshness",
                          "description_consistency", "keyword_stuffing",
                          "fluff", "unproven_superlatives"})

    def test_score_claim_constants_and_honesty_sentence(self):
        """Plan Section 1.3 S3 limb (a), ScoreObject constants. Oracle: plan Section 5.1 ScoreObject and brief Section 5.8 IM7-BRK-14 landing, claim_type is a constant from the closed set holding exactly one value, signal_presence_only, and validated_predictor is the boolean false; the honesty sentence is the fixed brief Section 5.5 item 121 sentence."""
        results = checks.run_checks(score_a_page(), make_facts(), audit_date=AUDIT_DATE)
        score = checks.compute_score(results)
        self.assertEqual(field(score, "claim_type"), "signal_presence_only")
        self.assertIs(field(score, "validated_predictor"), False)
        self.assertEqual(field(score, "honesty_sentence"), HONESTY_SENTENCE)

    def test_evidence_cap_applies_on_counts_not_earned(self):
        """Plan Section 1.3 S3 limb (a), score computation, evidence cap. Oracle: brief Section 5.7, the score carries the evidence cap of 39 where citations, statistics, and quotations all count zero, the cap quantities named per check being the distinct citation target count, the statistic token count, and the attributed span count; on this page the quotations check earns 0.25 from an unattributed span while its attributed count stands at zero, and the other two counts stand at zero, so the cap operates on counts and not on earned values; the uncapped hand sum is 58.75, so the value is 39.0, the cap status stands, and the band is poor below 40."""
        sentences = [
            "Macroforge is a campaign workbench for agent teams.",
            "Adoption reached many regions this year.",
            '"Teams plan better together" appeared in the notes.',
            "Versus Rivalforge for planning work.",
            "The guide explains weekly planning rhythm for teams.",
            "Updated: 2026-08-16",
        ]
        page = make_page(paragraphs=[[s] for s in sentences])
        results = checks.run_checks(page, make_facts(), audit_date=AUDIT_DATE)
        by_id = {field(r, "check_id"): r for r in results}
        self.assertEqual(field(by_id["quotations"], "earned"), 0.25)
        score = checks.compute_score(results)
        self.assertEqual(field(score, "value"), 39.0)
        self.assertTrue(field(score, "cap_status"))
        self.assertEqual(field(score, "band"), "poor")

    def test_not_applicable_weight_redistributed(self):
        """Plan Section 1.3 S3 limb (a), score computation with redistribution. Oracle: brief Section 5.7 and grill Q9 and Q15, not applicable weight is redistributed and disclosed; with description_consistency not applicable on a non product page, the scored page hand sum over the nine applicable checks is 76.0 over an applicable weight of 92, giving 82.6 at one decimal place, band strong."""
        results = checks.run_checks(score_a_page(),
                                    make_facts(is_product_page=False),
                                    audit_date=AUDIT_DATE)
        score = checks.compute_score(results)
        self.assertEqual(field(score, "value"), 82.6)
        self.assertEqual(field(score, "band"), "strong")
        basis = field(score, "applicable_basis")
        self.assertEqual(field(basis, "applicable_weight"), 92)
        self.assertNotIn("description_consistency",
                         field(basis, "applicable_checks"))

    def test_plain_page_score_floor_case(self):
        """Plan Section 1.3 S3 limb (a), score computation for the non empty case. Oracle: brief Section 5.7 score rule applied by hand; on this plain non product page the seven non inverted applicable checks earn 0, and the three inverted checks earn full credit on a clean page (keyword_stuffing 1.0, fluff 1.0, unproven_superlatives 1.0), so the hand sum is 22.0 over the applicable weight of 92 with description_consistency not applicable, giving 23.9 at one decimal place, band poor under grill Q9. This is not the empty extraction case, whose score expectation stands blocked at Part B entry B4 and is asserted nowhere in this file."""
        page = make_page(paragraphs=[["The session covers planning and review."]])
        results = checks.run_checks(page, make_facts(is_product_page=False),
                                    audit_date=AUDIT_DATE)
        score = checks.compute_score(results)
        self.assertEqual(field(score, "value"), 23.9)
        self.assertEqual(field(score, "band"), "poor")


class TestEmptyExtractionEndState(unittest.TestCase):
    def test_empty_page_every_check_not_applicable(self):
        """Plan Section 1.3 S3 limb (d) proceeding limb and Part B entry B4 proceeding tests. Oracle: Part B entry B4, the empty end state itself pins (stored, EXT_EMPTY, audit record produced, every check not applicable), as a separate row from the blocked score expectation; no score value, band, or basis is asserted here."""
        page = make_page(raw_text="", sentences=[], word_count=0)
        results = checks.run_checks(page, make_facts(), audit_date=AUDIT_DATE)
        self.assertEqual(len(results), 10)
        for r in results:
            self.assertEqual(field(r, "status"), "not_applicable")


class TestSectionBreakdown(unittest.TestCase):
    def test_citations_breakdown_marks_by_section(self):
        """Plan Section 1.3 S3 limb (a), evidence spans and section attribution. Oracle: brief Section 5.7 IM7-DIV-2 landing, a span is attributed to the section holding the span start offset, and the three evidence checks carry the breakdown with a present or absent mark for each section, present where at least one span is attributed and absent where none is; the one citation here stands in the second section only."""
        first = "Opening prose stands here without any counted evidence inside it."
        heading = "Details"
        second = "The detailed prose holds https://example.org/a inside it for readers."
        running = first + "\n\n" + heading + "\n\n" + second
        sections = [
            {"heading_text": None, "start": 0, "end": len(first),
             "references_section": False},
            {"heading_text": heading, "start": len(first) + 2,
             "end": len(running), "references_section": False},
        ]
        links = [link("https://example.org/a", "https://example.org/a",
                      running.index("https://example.org/a"))]
        page = make_page(raw_text=running, sentences=[first, second],
                         headings=[{"text": heading}], sections=sections,
                         links=links, word_count=len(running.split()))
        r = run(page)["citations"]
        breakdown = field(r, "section_breakdown")
        marks = [field(entry, "mark") for entry in breakdown]
        self.assertEqual(marks, ["absent", "present"])


class TestS3TimingBound(unittest.TestCase):
    def test_ten_checks_within_10_seconds(self):
        """Plan Section 1.5 timing bounds. Oracle: plan Section 1.5, S3, the ten checks over one extracted page, 10 seconds, a plan design value at the stated test scale of one extracted page; no scale statement is owed for this slice."""
        start = time.perf_counter()
        checks.run_checks(score_a_page(), make_facts(), audit_date=AUDIT_DATE)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 10.0)


def load_fixture_json(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


class TestConformanceS3RecordsLimb(unittest.TestCase):
    """The Section 5.5 conformance fixtures for the three reading
    forms run from this slice onward on trade T-7, against S3
    records in their pinnable limbs only (plan Section 1.3 S3
    conformance timing). Rendering itself stands at S9 and is
    not asserted here; the Simple limb asserted here is the
    score basis data the record carries, and every status
    dependent limb stands blocked at Part B entry B1.
    Fixtures: catalogue-w3.md entries W3-F1 to W3-F3.
    """

    def test_advanced_recomputation_of_score_from_check_fields(self):
        """Plan Section 1.3 S3 conformance timing, Advanced limb. Oracle: brief Section 5.5 conformance check for Advanced, recomputation of the score from check fields within the rounding the brief states; fixture w3-record-score-a.json carries the ten CheckResults and the ScoreObject for the scored page, whose hand computed value is 84.0, and the product score computation over the fixture check fields reproduces it with its band and cap status."""
        record = load_fixture_json("w3-record-score-a.json")
        score = checks.compute_score(record["checks"])
        self.assertEqual(field(score, "value"), 84.0)
        self.assertEqual(field(score, "band"),
                         field(record["score"], "band"))
        self.assertEqual(field(score, "cap_status"),
                         field(record["score"], "cap_status"))

    def test_advanced_span_check_against_supplied_text(self):
        """Plan Section 1.3 S3 conformance timing, Advanced limb. Oracle: brief Section 5.5 conformance check for Advanced, span check, each excerpt matches the supplied text at its stated offsets; the supplied text is fixture w3-page-score-a.txt and the spans stand in fixture w3-record-score-a.json, hand authored at the catalogue entry."""
        record = load_fixture_json("w3-record-score-a.json")
        with open(os.path.join(FIXTURES, "w3-page-score-a.txt"),
                  "r", encoding="utf-8") as handle:
            text = handle.read()
        seen = 0
        for check in record["checks"]:
            for span in check["evidence_spans"]:
                seen += 1
                self.assertEqual(text[span["start"]:span["end"]],
                                 span["excerpt"])
        self.assertEqual(seen, 6)

    def test_agentic_cross_form_equality_on_shared_fields(self):
        """Plan Section 1.3 S3 conformance timing, Agentic limb. Oracle: brief Section 5.5 conformance check for Agentic, cross form equality holds on shared fields against the Advanced artefact for the same run; fixtures w3-record-score-a.json and w3-record-score-a-agentic.json carry the same run in the two forms, and their shared S3 fields (per check earned value, reason code, and evidence spans, and the score value and band) stand equal, and the product score computation over the Agentic form check fields gives the same value."""
        advanced = load_fixture_json("w3-record-score-a.json")
        agentic = load_fixture_json("w3-record-score-a-agentic.json")["report"]
        def shared(record):
            return [(c["check_id"], c["earned"], c["reason_code"],
                     c["evidence_spans"]) for c in record["checks"]]
        self.assertEqual(shared(advanced), shared(agentic))
        self.assertEqual(advanced["score"]["value"], agentic["score"]["value"])
        self.assertEqual(advanced["score"]["band"], agentic["score"]["band"])
        score = checks.compute_score(agentic["checks"])
        self.assertEqual(field(score, "value"), advanced["score"]["value"])

    def test_simple_basis_data_limb(self):
        """Plan Section 1.3 S3 conformance timing, Simple limb in its pinnable form. Oracle: brief Section 5.5 common carry and the Simple conformance statement that the score stands with its basis stated; at the S3 records limb the basis the record carries names the applicable checks and the applicable weight, here the ten checks and 100, and the honesty sentence field carries the fixed item 121 sentence verbatim."""
        record = load_fixture_json("w3-record-score-a.json")
        basis = record["score"]["applicable_basis"]
        self.assertEqual(basis["applicable_weight"], 100)
        self.assertEqual(len(basis["applicable_checks"]), 10)
        self.assertEqual(record["score"]["honesty_sentence"], HONESTY_SENTENCE)


# The joined entry 13 and item 126 table, hand transcribed from
# the plan decisions section (Decisions D-KF-13, the joined
# enumeration table IM2-BRK-11): row, token, precedence class,
# exit code. Classes for the X rows stand as decision
# D-KF-13-CLASS assigns them, except row X-13 (decision
# D-KF-18-TEMP) and rows X-14 to X-16 (decision D-KF-13-ROWS).
EXPECTED_JOINED_TABLE = [
    ("U-1", "UNKNOWN_PRODUCT", "usage", 2),
    ("U-2", "PRODUCT_READD_CHANGED", "usage", 2),
    ("U-3", "ROUND_FIELD_OUT_OF_SET", "usage", 2),
    ("U-4", "UNKNOWN_ROUND", "usage", 2),
    ("U-5", "CONTROL_CAP_EXCEEDED", "usage", 2),
    ("U-6", "HOME_MISSING", "usage", 2),
    ("U-7", "ROUND_REPEATED", "usage", 2),
    ("U-8", "MALFORMED_CALL", "usage", 2),
    ("U-9", "WATCHPLAN_SIZE_EXCEEDED", "usage", 2),
    ("U-10", "WATCH_TARGET_COUNT_EXCEEDED", "usage", 2),
    ("U-11", "WATCH_ESTATE_WITH_TARGETS", "usage", 2),
    ("U-12", "WATCH_DUPLICATE_TARGET", "usage", 2),
    ("U-13", "WATCH_NO_TARGETS", "usage", 2),
    ("I-1", "JOURNAL_CAP_EXCEEDED", "integrity", 5),
    ("I-2", "JOURNAL_VERIFY_FAILED", "integrity", 5),
    ("D-1", "ROUND_LABEL_EXISTS", "domain", 3),
    ("X-1", "CONFIG_INVALID", "integrity", 5),
    ("X-2", "ANCHOR_PATH_INSIDE_HOME", "usage", 2),
    ("X-3", "LIMIT_EXCEEDED", "integrity", 5),
    ("X-4", "SUPPLIED_PATH_UNSAFE", "integrity", 5),
    ("X-5", "VALIDATION_FAILED", "usage", 2),
    ("X-6", "DUPLICATE_IMPORT", "domain", 3),
    ("X-7", "CONTRADICTORY_IMPORT", "domain", 3),
    ("X-8", "UNCOVERED_IMPORT_FORM", "usage", 2),
    ("X-9", "DESTINATION_EXISTS", "domain", 3),
    ("X-10", "WRITE_CONTENDED", "integrity", 5),
    ("X-11", "LIMIT_RAISE_REPEATED", "usage", 2),
    ("X-12", "LOCK_UNAVAILABLE", "integrity", 5),
    ("X-13", "TEMPORARY_LOST", "integrity", 5),
    ("X-14", "PAGE_EXTRACTION_FAILED", "usage", 2),
    ("X-15", "ROBOTS_DECODING_FAILED", "usage", 2),
    ("X-16", "IMPORT_VALIDATION_FAILED", "usage", 2),
]

CLASS_TO_EXIT = {"usage": 2, "domain": 3, "integrity": 5}


def product_table():
    rows = []
    for entry in errors.ERROR_VOCABULARY:
        rows.append((field(entry, "row"), field(entry, "token"),
                     field(entry, "precedence_class"),
                     field(entry, "exit_code")))
    return rows


class TestJoinedErrorTableF20(unittest.TestCase):
    """Pinning condition F-20 (plan Section 1.3 S3 limb (a)):
    the joined entry 13 and item 126 table stands tested by a
    two way coverage trace run over the table itself. The
    expected table above is hand transcribed from the plan
    joined table, not recorded from any run.
    """

    def test_forward_every_brief_condition_to_exactly_one_value(self):
        """Plan Section 1.3 S3 limb (a), F-20 forward trace. Oracle: plan entry 13 enumeration (rows U-1 to U-13, I-1, I-2, D-1, X-1 to X-16) as landed in the joined table; every failure condition row stands in the product vocabulary exactly once, under its one token."""
        got = product_table()
        for row in EXPECTED_JOINED_TABLE:
            self.assertEqual(got.count(row), 1, row)
        expected_tokens = [t for _, t, _, _ in EXPECTED_JOINED_TABLE]
        self.assertEqual(len(set(expected_tokens)), len(expected_tokens))

    def test_backward_every_value_back_to_one_condition(self):
        """Plan Section 1.3 S3 limb (a), F-20 backward trace. Oracle: plan entry 13, the vocabulary is closed over the traced conditions and no value outside the set may ship; every product vocabulary entry is one of the expected rows, no token repeats, and the product set and the expected set stand equal at 32 rows."""
        got = product_table()
        self.assertEqual(len(got), 32)
        self.assertEqual(set(got), set(EXPECTED_JOINED_TABLE))
        tokens = [t for _, t, _, _ in got]
        self.assertEqual(len(set(tokens)), len(tokens))

    def test_every_value_to_exactly_one_exit_code(self):
        """Plan Section 1.3 S3 limb (a), F-20 exit trace. Oracle: plan item 126 table, the mapping from values to codes runs through the precedence classes, usage errors to 2, domain errors to 3, integrity refusals to 5; every row of the product vocabulary carries the one code its class assigns, and no row carries any other code."""
        for row, token, cls, code in product_table():
            self.assertEqual(code, CLASS_TO_EXIT[cls], (row, token))

    def test_shared_refusal_value_and_distinguishing_field(self):
        """Plan Section 1.3 S3 limb (a), F-20 shared refusal row. Oracle: plan entry 13 row I-1 and decision D-KF-13-DIST, one value serves both the ordinary cap refusal and the import preflight refusal, listed once, and the two refusals are distinguished by the structured field refusal_context, with values append_cap and import_preflight, carried beside limit_number holding 39 or 40; the table names that distinguishing field in the row itself."""
        matches = [e for e in errors.ERROR_VOCABULARY
                   if field(e, "token") == "JOURNAL_CAP_EXCEEDED"]
        self.assertEqual(len(matches), 1)
        entry = matches[0]
        self.assertEqual(field(entry, "row"), "I-1")
        self.assertEqual(field(entry, "distinguishing_field"),
                         "refusal_context")
        self.assertEqual(set(field(entry, "distinguishing_values")),
                         {"append_cap", "import_preflight"})
        self.assertEqual(set(field(entry, "limit_numbers")), {39, 40})

    def test_code_4_returned_by_no_version_1_invocation(self):
        """Plan Section 1.3 S3 limb (a), F-20 code 4 row, and plan item 126 table row for code 4. Oracle: code 4 stands for the gate, the Q27 claim conformance check, a pre-release check and not a product operation, and no version 1 product invocation returns it; the product vocabulary assigns exit code 4 to no value, and the set of codes it assigns is exactly 2, 3, and 5."""
        codes = {code for _, _, _, code in product_table()}
        self.assertNotIn(4, codes)
        self.assertEqual(codes, {2, 3, 5})

    def test_value_1_unassigned(self):
        """Plan Section 1.3 S3 limb (a), F-20 value 1 row, and plan item 126 table row for code 1. Oracle: value 1 stands unassigned as a product outcome, no brief passage assigns it, and the product never returns it in version 1; the product vocabulary assigns exit code 1 to no value."""
        codes = {code for _, _, _, code in product_table()}
        self.assertNotIn(1, codes)


if __name__ == "__main__":
    unittest.main()
