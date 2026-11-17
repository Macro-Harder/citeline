"""Guide and reporting.

Defect pins, and, written before the cures they pin. Entry:
the guide walk in _record_states_failed_control judges the
public attributes and the _asdict form of str, int, and
float subclass carriers, while reporting._plain passes such
a carrier through as a scalar before any _asdict limb and
before any object dict limb, so the draft suppresses on
fields the rendering never states. A carrier the rendering
passes through as a scalar must stand judged at the draft
on the rendering terms. Entry: the rendering reading
notices a non dict mapping returned by an _asdict form
through its items call, while the guide walk yields the
fields of that return only where the return stands as a
dict, so a failed control stated in a mapping proxy return,
a custom Mapping return, or an items only return escapes
the draft whole. Such a return must stand judged by the
draft as by the rendering. Entry: the guide walk judges the
value standing under a flag name by its raw truthiness,
while the rendering judges the value as reporting._plain
converts it, so a flag whose raw value stands truthy and
whose converted value stands falsy states the failed
control at the draft and states nothing at the rendering,
and a flag whose raw value stands falsy and whose converted
value stands truthy states it at the rendering alone. The
flag value must stand judged on the converted terms at both
readings. Oracle: the round 17 findings register and
disposition, ruling (e) and Section 3 seat F6, the round 17
guide attack paper at finding and, the Red paper at
finding, and the Yellow paper at finding.

Copyright: J.P. Picard aka Macro-Harder."""

import math
import unittest
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

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


def raw_asdict_record(returned, fields=None):
    """An attribute carrying record whose _asdict form
    returns the supplied form as it stands, with no copy
    made, so a non dict mapping return reaches the two
    readings in its own form."""

    def _asdict(self):
        return self._returned

    cls = type("RawAsdictRecord", (), {"_asdict": _asdict})
    obj = cls()
    obj._returned = returned
    if fields:
        obj.__dict__.update(fields)
    return obj


class SlotsAsdict:
    """An _asdict record standing on empty slots, with
    no object dict at all, returning its mapping as it
    stands."""

    __slots__ = ("_mapping",)

    def __init__(self, mapping):
        self._mapping = mapping

    def _asdict(self):
        return self._mapping


class CustomMapping(Mapping):
    """A mapping standing on the collections abstract
    base class, its entries held under a private holder
    attribute, answering the mapping contract whole and
    standing as no dict."""

    def __init__(self, entries):
        self._entries = dict(entries)

    def __getitem__(self, key):
        return self._entries[key]

    def __iter__(self):
        return iter(self._entries)

    def __len__(self):
        return len(self._entries)


class ItemsOnly:
    """A form answering items alone, its entries held
    under a private holder attribute, standing as no
    dict and as no Mapping."""

    def __init__(self, entries):
        self._entries = dict(entries)

    def items(self):
        return self._entries.items()


class StrCarrier(str):
    """A str subclass carrier. Its instance dict stands
    as its attribute fields, and an _asdict form stands
    supplied per instance where a case states one."""


class IntCarrier(int):
    """An int subclass carrier, in the form of the str
    carrier."""


class FloatCarrier(float):
    """A float subclass carrier, in the form of the str
    carrier."""


class BytesCarrier(bytes):
    """A bytes subclass carrier, standing outside the
    scalar pass of the conversion."""


class DecimalCarrier(Decimal):
    """A Decimal subclass carrier, standing outside the
    scalar pass of the conversion."""


def scalar_with_flag(cls, value, name="control_failed"):
    instance = cls(value)
    instance.__dict__[name] = True
    return instance


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
# Entry: a str, int, or float subclass carrier stands judged at
# the draft on the rendering terms, the rendering passing the
# carrier through as a scalar, so its public attributes and its
# _asdict form state nothing at either reading.
# ----------------------------------------------------------------

class Test006ScalarSubclassCarriers(unittest.TestCase):

    def test_str_subclass_public_flag_stands_escaped_on_both(self):
        record = {"member": scalar_with_flag(StrCarrier, "x")}
        assert_agree_escaped(self, record)

    def test_int_subclass_public_flag_stands_escaped_on_both(self):
        record = {"member": scalar_with_flag(IntCarrier, 3)}
        assert_agree_escaped(self, record)

    def test_float_subclass_public_flag_stands_escaped_on_both(self):
        record = {"member": scalar_with_flag(FloatCarrier, 1.5)}
        assert_agree_escaped(self, record)

    def test_str_subclass_dressed_flag_name_stands_escaped(self):
        record = {"member": scalar_with_flag(
            StrCarrier, "x", name="Control_Failed")}
        assert_agree_escaped(self, record)

    def test_str_subclass_asdict_form_stands_unjudged_on_both(self):
        carrier = StrCarrier("x")
        carrier._asdict = lambda: {"control_failed": True}
        assert_agree_escaped(self, {"member": carrier})

    def test_int_subclass_asdict_form_stands_unjudged_on_both(self):
        carrier = IntCarrier(3)
        carrier._asdict = lambda: {"control_failed": True}
        assert_agree_escaped(self, {"member": carrier})

    def test_scalar_carrier_inside_a_list_item(self):
        record = {"items": [scalar_with_flag(StrCarrier, "x")]}
        assert_agree_escaped(self, record)

    def test_scalar_carrier_held_on_a_public_attribute(self):
        record = {"wrapper": Bag(
            {"inner": scalar_with_flag(IntCarrier, 3)})}
        assert_agree_escaped(self, record)

    def test_scalar_carrier_inside_an_asdict_mapping(self):
        record = {"wrapper": raw_asdict_record(
            {"member": scalar_with_flag(FloatCarrier, 1.5)})}
        assert_agree_escaped(self, record)

    def test_scalar_carrier_private_flag_control_holds(self):
        record = {"member": scalar_with_flag(
            StrCarrier, "x", name="_control_failed")}
        assert_agree_escaped(self, record)

    def test_bytes_subclass_carrier_control_holds_suppressed(self):
        # A bytes carrier stands in no scalar pass of the
        # conversion, so both readings reach its object
        # dict as they stand: the scalar cure stands on
        # the str, int, and float precedence alone.
        record = {"member": scalar_with_flag(BytesCarrier, b"x")}
        assert_agree_suppressed(self, record)

    def test_decimal_subclass_carrier_control_holds_suppressed(self):
        record = {"member": scalar_with_flag(
            DecimalCarrier, "1.5")}
        assert_agree_suppressed(self, record)


# ----------------------------------------------------------------
# Entry: a non dict mapping returned by an _asdict form stands
# judged by the draft as by the rendering, on its items alone.
# ----------------------------------------------------------------

class Test007NonDictMappingReturns(unittest.TestCase):

    def test_mapping_proxy_return_suppresses_the_draft(self):
        record = {"wrapper": raw_asdict_record(
            MappingProxyType({"control_failed": True}))}
        assert_agree_suppressed(self, record)

    def test_mapping_proxy_return_nested_flag(self):
        record = {"wrapper": raw_asdict_record(
            MappingProxyType(
                {"round": {"control_failed": True}}))}
        assert_agree_suppressed(self, record)

    def test_mapping_proxy_return_dressed_flag_name(self):
        record = {"wrapper": raw_asdict_record(
            MappingProxyType({"Control_Failed": True}))}
        assert_agree_suppressed(self, record)

    def test_custom_mapping_return_suppresses_the_draft(self):
        record = {"wrapper": raw_asdict_record(
            CustomMapping({"control_failed": True}))}
        assert_agree_suppressed(self, record)

    def test_items_only_return_suppresses_the_draft(self):
        record = {"wrapper": raw_asdict_record(
            ItemsOnly({"control_failed": True}))}
        assert_agree_suppressed(self, record)

    def test_non_dict_mapping_return_false_flag_control(self):
        record = {"wrapper": raw_asdict_record(
            MappingProxyType({"control_failed": False}))}
        assert_agree_escaped(self, record)

    def test_dict_return_control_holds_suppressed(self):
        record = {"wrapper": raw_asdict_record(
            {"control_failed": True})}
        assert_agree_suppressed(self, record)

    def test_asdict_list_return_stands_in_bounded_form(self):
        # The Yellow bounded observation, standing in its
        # bounded form outside this cure: a list return
        # stands outside the mapping contract, escaped at
        # the draft and raising at the rendering.
        record = {"wrapper": raw_asdict_record(
            [("control_failed", True)])}
        assert_escaped(self, draft_of(record))
        with self.assertRaises(AttributeError):
            reporting.render(record, form="advanced")


# ----------------------------------------------------------------
# Entry: a flag value stands judged on the converted terms at both
# readings, on the Red battery of non finite float and Decimal
# values and empty object values, and on the Yellow battery of an
# attribute record converting to an empty plain form.
# ----------------------------------------------------------------

class Test008FlagValueConvertedTerms(unittest.TestCase):

    def test_non_finite_float_flag_values(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                assert_agree_escaped(
                    self, {"control_failed": value})

    def test_non_finite_decimal_flag_values(self):
        for value in (Decimal("NaN"), Decimal("Infinity"),
                      Decimal("-Infinity")):
            with self.subTest(value=value):
                assert_agree_escaped(
                    self, {"control_failed": value})

    def test_non_finite_flag_on_an_object_attribute(self):
        for value in (math.nan, Decimal("NaN")):
            with self.subTest(value=value):
                record = {"wrapper": Bag(
                    {"control_failed": value})}
                assert_agree_escaped(self, record)

    def test_empty_object_flag_value_stands_escaped_on_both(self):
        assert_agree_escaped(self, {"control_failed": Bag()})

    def test_all_private_object_flag_value_stands_escaped(self):
        record = {"control_failed": Bag({"_held": 1})}
        assert_agree_escaped(self, record)

    def test_empty_asdict_record_flag_value_stands_escaped(self):
        record = {"control_failed": raw_asdict_record({})}
        assert_agree_escaped(self, record)

    def test_empty_slots_asdict_flag_value_stands_escaped(self):
        record = {"control_failed": SlotsAsdict({})}
        assert_agree_escaped(self, record)

    def test_empty_object_flag_value_nested_in_a_record(self):
        record = {"outer": {"control_failed": Bag()}}
        assert_agree_escaped(self, record)

    def test_non_finite_flag_value_inside_an_asdict_mapping(self):
        record = {"wrapper": raw_asdict_record(
            {"control_failed": math.nan})}
        assert_agree_escaped(self, record)

    def test_decimal_zero_flag_value_on_converted_terms(self):
        # The conversion states a finite Decimal in its
        # string form, a truthy value at the rendering,
        # so the draft stands judged on that same term.
        assert_agree_suppressed(
            self, {"control_failed": Decimal("0")})

    def test_flag_value_with_a_public_field_control_holds(self):
        record = {"control_failed": Bag({"held": 1})}
        assert_agree_suppressed(self, record)

    def test_flag_value_asdict_with_a_field_control_holds(self):
        record = {"control_failed": raw_asdict_record(
            {"held": 1})}
        assert_agree_suppressed(self, record)

    def test_empty_plain_flag_values_control_holds(self):
        for value in ({}, [], (), 0, ""):
            with self.subTest(value=value):
                assert_agree_escaped(
                    self, {"control_failed": value})


if __name__ == "__main__":
    unittest.main()
