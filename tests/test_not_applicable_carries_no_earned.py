"""Repair test: not applicable earned.

Oracle: the settled rule, a
check with status not_applicable carries no earned
fraction and no presence reason; description
consistency on a supplied file audit stands with no
earned 1.0 and no DESC_PRESENT.
"""

import unittest

from citeline import checks

AUDIT_DATE = "2026-08-20"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


class TestR19085NotApplicableCarriesNoEarned(unittest.TestCase):
    def test_not_applicable_description_check_is_bare(self):
        sentence = "Macroforge is a campaign workbench for agent teams."
        page = {
            "running_text": sentence,
            "sentences": [sentence],
            "paragraphs": [[sentence]],
            "headings": [],
            "sections": [{
                "heading_text": None, "start": 0,
                "end": len(sentence), "references_section": False,
            }],
            "links": [],
            "blockquotes": [],
            "lists": [],
            "tables": [],
            "date_strings": [],
            "canonical_link_element": None,
            "meta_robots": None,
            "word_count": len(sentence.split()),
            "extracted_text_length": len(sentence),
            "extraction_notes": [],
        }
        facts = {
            "product_name": "Macroforge",
            "aliases": ["Macroforge"],
            "category_terms": ["workbench"],
            "canonical_line": sentence,
            "is_product_page": False,
            "domain": "macroforge.example",
            "competitors": [{"name": "Rivalforge",
                             "aliases": ["Rivalforge"]}],
        }
        results = checks.run_checks(page, facts, audit_date=AUDIT_DATE)
        by_id = {field(r, "check_id"): r for r in results}
        r = by_id["description_consistency"]
        self.assertEqual(field(r, "status"), "not_applicable")
        self.assertIsNone(field(r, "earned"))
        self.assertIsNone(field(r, "reason_code"))


if __name__ == "__main__":
    unittest.main()
