"""Repair test.

Oracle: the audit record finding the repair item,
disposed [defect] in the audit record
Part B: the Simple query set report renders the marker list
version as a raw Python dict. The cure: the Simple form
renders it as text an operator can read.
"""

import unittest

from citeline import reporting


class TestP8O04QuerySetMarkerVersionPlain(unittest.TestCase):

    def _body(self, marker):
        return {
            "product_id": "p-x",
            "query_set_version": 1,
            "total_count": 2,
            "interrogative_count": 1,
            "comparison_count": 0,
            "named_product_count": 1,
            "bare_topic_count": 1,
            "duplicate_count": 0,
            "naming_none_count": 0,
            "marker_list_version": marker,
        }

    def test_marker_version_not_rendered_as_raw_dict(self):
        text = reporting.render(self._body(
            {"recorded": False, "state": "not_recorded"}), "simple")
        self.assertNotIn("{'recorded': False", text)
        self.assertNotIn("'state': 'not_recorded'", text)
        self.assertNotIn("False", text)

    def test_marker_version_states_not_recorded_in_words(self):
        text = reporting.render(self._body(
            {"recorded": False, "state": "not_recorded"}), "simple")
        self.assertIn("marker list version", text)
        self.assertIn("no marker list version stands recorded", text)

    def test_recorded_marker_version_renders_its_value(self):
        text = reporting.render(self._body(
            {"recorded": True, "state": "recorded", "version": 3}),
            "simple")
        self.assertNotIn("{'recorded': True", text)
        self.assertIn("marker list version 3", text)


if __name__ == "__main__":
    unittest.main()
