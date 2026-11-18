"""Repair test: description consistency.

Oracle: brief Section 5.7, full credit only where the
canonical line appears verbatim after whitespace
normalisation; a canonical line differing only in
spacing or line breaks earns full credit instead of
DESC_DRIFT or 0.
"""

import unittest

from citeline import checks

AUDIT_DATE = "2026-08-20"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def make_facts():
    return {
        "product_name": "Macroforge",
        "aliases": ["Macroforge"],
        "category_terms": ["workbench"],
        "canonical_line": "Macroforge is a campaign workbench for agent teams.",
        "is_product_page": True,
        "domain": "macroforge.example",
        "competitors": [{"name": "Rivalforge", "aliases": ["Rivalforge"]}],
    }


class TestR19002DescriptionWhitespace(unittest.TestCase):
    def test_verbatim_after_whitespace_normalisation(self):
        raw = ("Intro line stands here for the reader.\n\n"
               "Macroforge is a  campaign\nworkbench   for agent teams.")
        page = {
            "running_text": raw,
            "sentences": [
                "Intro line stands here for the reader.",
                "Macroforge is a  campaign\nworkbench   for agent teams.",
            ],
            "paragraphs": [],
            "headings": [],
            "sections": [{
                "heading_text": None, "start": 0,
                "end": len(raw), "references_section": False,
            }],
            "links": [],
            "blockquotes": [],
            "lists": [],
            "tables": [],
            "date_strings": [],
            "canonical_link_element": None,
            "meta_robots": None,
            "word_count": len(raw.split()),
            "extracted_text_length": len(raw),
            "extraction_notes": [],
        }
        results = checks.run_checks(page, make_facts(), audit_date=AUDIT_DATE)
        by_id = {field(r, "check_id"): r for r in results}
        r = by_id["description_consistency"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "DESC_PRESENT")


if __name__ == "__main__":
    unittest.main()
