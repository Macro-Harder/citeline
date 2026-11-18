"""Journal family.

The repair carries no repair entry. These
tests pin the standing verdicts of this repair on the
tree as it stands: the repair cure at standing
whole, a plant at any of the first seven readings of
the config handle in write_config standing refused in
the remedy form, a plant placed before the eighth and
last reading executes standing seen by that reading
and refused in the same form, so the eighth reading
stands proved a real reading, and a plain config write
landing whole. The plant at the return of the eighth
and last reading stands in its bounded position in its
standing form, as the repair record states it,
and no test here pins that form, neither as a defect
nor as cured. The batch intent write plant stands
bounded outside this charge in the same form. No
product module stands edited by this repair. Homes are
scratch homes under a temporary directory. No test
here touches a standing test item or a governed
ground: CARRY and CARRY stand untouched in exact form."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal
from citeline.errors import ConfigError


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def read_text(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def plant_on_counted_fstat(self, target, outside, plant_at,
                               before=False):
        real_fstat = os.fstat
        state = {"count": 0}

        def wrapper(fd):
            try:
                link = os.readlink("/proc/self/fd/%d" % fd)
            except OSError:
                link = None
            if link == target:
                state["count"] += 1
                if state["count"] == plant_at and before:
                    os.link(target, outside)
                    return real_fstat(fd)
            info = real_fstat(fd)
            if link == target and state["count"] == plant_at \
                    and not before:
                os.link(target, outside)
            return info

        return mock.patch.object(os, "fstat", wrapper)

    def assert_refused_in_remedy_form(self, plant_at, before=False):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_fstat(path, outside, plant_at,
                                          before=before):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        with open(outside, "rb") as handle:
            self.assertNotIn(b"99", handle.read())
        self.assertFalse(os.path.lexists(path))


class ConfigEighthReadingStandingTests(HomeCase):
    def test_r14_f1_plant_at_seventh_reading_return_refused(self):
        self.assert_refused_in_remedy_form(7)

    def test_r14_f1_plant_at_sixth_reading_return_refused(self):
        self.assert_refused_in_remedy_form(6)

    def test_r14_f1_plant_at_fifth_reading_return_refused(self):
        self.assert_refused_in_remedy_form(5)

    def test_r14_f1_plant_at_fourth_reading_return_refused(self):
        self.assert_refused_in_remedy_form(4)

    def test_r14_f1_plant_at_third_reading_return_refused(self):
        self.assert_refused_in_remedy_form(3)

    def test_r14_f1_plant_at_second_reading_return_refused(self):
        self.assert_refused_in_remedy_form(2)

    def test_r14_f1_plant_at_first_reading_leaves_standing_text_whole(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_fstat(path, outside, 1):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertTrue(os.path.lexists(path))
        self.assertEqual(self.read_text(path), "journal_length = 5\n")
        self.assertEqual(self.read_text(outside),
                         "journal_length = 5\n")

    def test_r14_f1_plant_before_eighth_reading_seen_and_refused(self):
        self.assert_refused_in_remedy_form(8, before=True)

    def test_r14_f1_config_write_plain_form_lands(self):
        journal.write_config(self.home, "journal_length = 99\n")
        path = journal.config_path(self.home)
        self.assertEqual(self.read_text(path), "journal_length = 99\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)


if __name__ == "__main__":
    unittest.main()
