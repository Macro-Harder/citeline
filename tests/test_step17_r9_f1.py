"""Journal family.

Each test pins one settled rule from the findings the settled record on the behaviour the register and
the settled disposition state. Homes are scratch
homes under a temporary directory. No test here
touches a standing test item or a governed ground."""

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

    def plant_on_counted_fstat(self, target, outside, plant_at):
        real_fstat = os.fstat
        state = {"count": 0}

        def wrapper(fd):
            info = real_fstat(fd)
            try:
                link = os.readlink("/proc/self/fd/%d" % fd)
            except OSError:
                link = None
            if link == target:
                state["count"] += 1
                if state["count"] == plant_at:
                    os.link(target, outside)
            return info

        return mock.patch.object(os, "fstat", wrapper)


class ConfigOpenTruncateTests(HomeCase):
    def test_r9_001_plant_at_open_judgement_leaves_standing_text_whole(self):
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

    def test_r9_001_plain_write_after_longer_text_leaves_no_tail(self):
        journal.write_config(
            self.home, "journal_length = 12345\n")
        journal.write_config(self.home, "journal_length = 9\n")
        path = journal.config_path(self.home)
        self.assertEqual(self.read_text(path), "journal_length = 9\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)


class ConfigPostWriteFinalJudgementTests(HomeCase):
    def test_r9_017_plant_at_post_write_rejudgement_refused(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_fstat(path, outside, 3):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        with open(outside, "rb") as handle:
            self.assertNotIn(b"99", handle.read())
        self.assertFalse(os.path.lexists(path))

    def test_r9_017_plant_at_pre_write_rejudgement_still_refused(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_fstat(path, outside, 2):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        with open(outside, "rb") as handle:
            self.assertNotIn(b"99", handle.read())
        self.assertFalse(os.path.lexists(path))

    def test_r9_017_config_write_plain_form_lands(self):
        journal.write_config(self.home, "journal_length = 99\n")
        path = journal.config_path(self.home)
        self.assertEqual(self.read_text(path), "journal_length = 99\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)


if __name__ == "__main__":
    unittest.main()
