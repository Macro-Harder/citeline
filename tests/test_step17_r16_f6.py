"""Step 17 round 16 fix seat F6 tests: guide and reporting.

Defect pins for entries S17-R16-012, S17-R16-013, and
S17-R16-014, written before the cures they pin.
Entry S17-R16-012: the draft reading judges object
fields through vars() with no exclusion, while the
rendering reading through reporting._plain drops
private attribute names on object records, so a record
carrying its content on a private attribute stands
judged on the draft reading and dropped on the
rendering reading. The two readings must stand on the
same field set of an object record.
Entry S17-R16-013: the rendering reading converts an
attribute carrying record by its _asdict form where
the record carries one, while the draft reading never
calls _asdict, so the mapping form stands carried on
the rendering reading and absent on the draft reading.
The mapping form must stand carried alike.
Entry S17-R16-014: the sentence argument of
passes_naming_test stands unguarded, so a non string
sentence raises the raw TypeError of the round through
the token reading. The sentence argument must stand
guarded in the form of the term guard of the same
call.
Oracle: the round 16 findings register and
disposition, ruling (e) and Section 3 seat F6, and
the round 16 guide attack paper.

Copyright: J.P. Picard aka Macro-Harder.
"""

import unittest
from collections import namedtuple

from citeline import guide, reporting

CANON = "Example Product answers questions."
GUIDE_NOTICE = ("a control in this round failed, and no "
                "action stands produced from this round")
ANSWERS = [{"named": False, "named_early": False,
            "cited": False}]


class Bag:
    """An attribute carrying record standing on a plain
    object dict, its fields standing as supplied, private
    names included."""

    def __init__(self, fields=None):
        if fields:
            self.__dict__.update(fields)


def asdict_record(mapping, fields=None):
    """An attribute carrying record whose fields stand
    in its _asdict form. The mapping stands as a class
    attribute, outside the object dict, so no reading of
    the object dict alone reaches it: only the _asdict
    conversion carries it. The object dict holds no flag
    unless one stands supplied in fields."""

    def _asdict(self):
        return dict(self._result)

    cls = type("AsdictRecord", (), {
        "_result": mapping, "_asdict": _asdict})
    obj = cls()
    if fields:
        obj.__dict__.update(fields)
    return obj


class SlotsAsdict:
    """An _asdict record standing on empty slots, with
    no object dict at all."""

    __slots__ = ("_mapping",)

    def __init__(self, mapping):
        self._mapping = mapping

    def _asdict(self):
        return dict(self._mapping)


def draft_of(record):
    return guide.draft_from_round(
        record, canonical_line=CANON, answers=ANSWERS)


def rendered_notice(record):
    rendered = reporting.render(record, form="advanced")
    if isinstance(rendered, dict):
        return rendered.get("control_failure_notice")
    return None


def assert_suppressed(case, draft):
    case.assertEqual(draft["actions"], [])
    case.assertEqual(
        draft.get("control_failure_notice"), GUIDE_NOTICE)


def assert_escaped(case, draft):
    case.assertEqual(
        [action["code"] for action in draft["actions"]],
        ["NOT_NAMED", "NOT_NAMED_EARLY", "NOT_CITED"])
    case.assertNotIn("control_failure_notice", draft)


def assert_agree_suppressed(case, record):
    case.assertEqual(
        rendered_notice(record), reporting.CONTROL_FAILURE_NOTICE)
    assert_suppressed(case, draft_of(record))


def assert_agree_escaped(case, record):
    case.assertIsNone(rendered_notice(record))
    assert_escaped(case, draft_of(record))


# ----------------------------------------------------------------
# Entry S17-R16-012: a record carrying its content on a
# private attribute of an object stands judged alike on
# both readings. The rendering conversion drops private
# attribute names on object records, so the draft walk
# stands on that same field set.
# ----------------------------------------------------------------

class Test012PrivateAttributeReading(unittest.TestCase):

    def test_private_flag_attribute_stands_dropped_on_both(self):
        record = {"wrapper": Bag({"_control_failed": True})}
        assert_agree_escaped(self, record)

    def test_record_held_on_a_private_attribute(self):
        record = {"wrapper": Bag(
            {"_round": {"control_failed": True}})}
        assert_agree_escaped(self, record)

    def test_object_held_on_a_private_attribute(self):
        inner = Bag({"control_failed": True})
        record = {"wrapper": Bag({"_inner": inner})}
        assert_agree_escaped(self, record)

    def test_private_attribute_inside_a_list_item(self):
        record = {"items": [Bag({"_control_flag": True})]}
        assert_agree_escaped(self, record)

    def test_dressed_private_attribute_names(self):
        for name in ("_Control_Failed", "_control-failed",
                     "_controlFailed"):
            with self.subTest(name=name):
                record = {"wrapper": Bag({name: True})}
                assert_agree_escaped(self, record)

    def test_private_flag_at_the_record_object_itself(self):
        record = Bag({"_control_failed": True,
                      "canonical_line": CANON})
        self.assertIsNone(rendered_notice(record))
        assert_escaped(self, draft_of(record))

    def test_public_attribute_control_holds_as_agreement(self):
        record = {"wrapper": Bag(
            {"round": {"control_failed": True}})}
        assert_agree_suppressed(self, record)

    def test_public_flag_attribute_control_holds(self):
        record = {"wrapper": Bag({"control_failed": True})}
        assert_agree_suppressed(self, record)

    def test_private_name_in_a_plain_record_still_judged(self):
        # A member name standing in a plain record stands
        # as written on both readings: the private name
        # exclusion of the conversion stands on object
        # records only, and a dict key carrying the flag
        # states the failed control at both readings.
        record = {"_control_failed": True}
        assert_agree_suppressed(self, record)

    def test_falsy_private_flag_stands_escaped_on_both(self):
        record = {"wrapper": Bag({"_control_failed": False})}
        assert_agree_escaped(self, record)


# ----------------------------------------------------------------
# Entry S17-R16-013: an object standing in the _asdict
# mapping form stands carried alike on both readings.
# The named tuple limb stands in its agreement form
# outside this cure: both readings read a tuple as a
# sequence before any _asdict limb, and its field names
# stand lost to both alike.
# ----------------------------------------------------------------

class Test013AsdictConversionReading(unittest.TestCase):

    def test_asdict_flag_suppresses_the_draft(self):
        record = {"wrapper": asdict_record(
            {"control_failed": True})}
        assert_agree_suppressed(self, record)

    def test_asdict_flag_nested_in_its_mapping(self):
        record = {"wrapper": asdict_record(
            {"round": {"control_failure": True}})}
        assert_agree_suppressed(self, record)

    def test_asdict_dressed_flag_name(self):
        record = {"wrapper": asdict_record(
            {"Control_Failed": True})}
        assert_agree_suppressed(self, record)

    def test_asdict_record_on_empty_slots(self):
        record = {"wrapper": SlotsAsdict(
            {"control_failed": True})}
        assert_agree_suppressed(self, record)

    def test_asdict_object_inside_a_list_item(self):
        record = {"items": [asdict_record(
            {"control_flag": True})]}
        assert_agree_suppressed(self, record)

    def test_asdict_object_held_on_a_public_attribute(self):
        record = {"wrapper": Bag(
            {"inner": asdict_record({"control_failed": True})})}
        assert_agree_suppressed(self, record)

    def test_asdict_false_flag_stands_escaped_on_both(self):
        record = {"wrapper": asdict_record(
            {"control_failed": False})}
        assert_agree_escaped(self, record)

    def test_asdict_form_stands_in_place_of_the_object_dict(self):
        # The rendering conversion reads the _asdict form
        # where the record carries one, before it reads
        # the object dict, so a flag standing in the
        # object dict alone, under no _asdict field,
        # states no failed control at either reading.
        record = {"wrapper": asdict_record(
            {"round": {}}, fields={"control_failed": True})}
        assert_agree_escaped(self, record)

    def test_named_tuple_limb_stands_in_agreement(self):
        flagged = namedtuple("Flagged", ["control_failed"])
        record = {"round": flagged(True)}
        assert_agree_escaped(self, record)


# ----------------------------------------------------------------
# Entry S17-R16-014: a non string sentence standing
# passed to passes_naming_test stands judged in the
# form of the term guard of the same call, read as no
# sentence, raising no raw error.
# ----------------------------------------------------------------

class Test014SentenceArgumentGuard(unittest.TestCase):

    def test_bytes_sentence_raises_nothing(self):
        self.assertFalse(guide.passes_naming_test(
            b"The Gadget grew", "Citeline",
            aliases=["Gadget"]))

    def test_integer_sentence_raises_nothing(self):
        self.assertFalse(guide.passes_naming_test(
            7, "Citeline", aliases=["Gadget"]))

    def test_list_sentence_raises_nothing(self):
        self.assertFalse(guide.passes_naming_test(
            ["The Gadget grew"], "Citeline",
            aliases=["Gadget"]))

    def test_record_sentence_raises_nothing(self):
        self.assertFalse(guide.passes_naming_test(
            {"sentence": "The Gadget grew"}, "Citeline",
            aliases=["Gadget"]))

    def test_float_sentence_raises_nothing(self):
        self.assertFalse(guide.passes_naming_test(
            2.5, "Citeline", category_terms=["Gadget"]))

    def test_non_string_sentence_at_the_contains_reading(self):
        self.assertFalse(guide._contains_term(
            b"The Gadget grew", "Gadget"))
        self.assertFalse(guide._contains_term(7, "Gadget"))

    def test_none_sentence_stands_as_no_sentence(self):
        self.assertFalse(guide.passes_naming_test(
            None, "Citeline", aliases=["Gadget"]))

    def test_string_sentence_controls_hold(self):
        self.assertTrue(guide.passes_naming_test(
            "The Gadget grew", "Citeline",
            aliases=["Gadget"]))
        self.assertFalse(guide.passes_naming_test(
            "Other grew", "Citeline", aliases=["Gadget"]))


if __name__ == "__main__":
    unittest.main()
