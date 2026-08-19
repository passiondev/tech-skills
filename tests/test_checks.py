#!/usr/bin/env python3
"""What CI's checks catch, asserted by running one against source built to fail.

`check.py` runs against this repository, so a green run says the repository is
clean. It says nothing about whether the check would notice if it were not.
A guard that silently stops guarding is worse than no guard, because the green
tick is read as evidence.

These tests close that gap the only way that works: point the check at a
throwaway file, write the shape it is supposed to reject, and assert it
complains.

Run:  python3 -m unittest discover -s tests
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERY_PATH = Path("plugins/rock/runtime/scripts/rock_query.py")


def _load_checks():
    """Import check.py by path — it is a script, not an importable module.

    Importing runs all of its checks against the real repository, which is
    harmless: they only append to `check.failures`, and every test here clears
    that list before it looks at it.
    """
    spec = importlib.util.spec_from_file_location(
        "check_py", ROOT / ".github" / "scripts" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = _load_checks()

# The three fetchers the caps check allows, reduced to what it reads.
FETCHERS = '''
def groups_of_types(client, name_filter, type_ids, limit):
    return client.get("Groups", params={"$filter": name_filter, "$top": limit + 1})


def get_capped(client, endpoint, params, limit):
    rows = client.get(endpoint, params={**params, "$top": limit + 1}) or []
    return rows[:limit], len(rows) > limit


def first(client, endpoint, params):
    rows = client.get(endpoint, params={**params, "$top": 1}) or []
    return rows[0] if rows else None
'''


class CheckTestCase(unittest.TestCase):
    """Runs one real check over a repository of our own making."""

    def run_check(self, fn, files):
        """Report what `fn` complains about, given `files` as the whole repo."""
        with tempfile.TemporaryDirectory() as tmp:
            for rel, source in files.items():
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            kept, real_root = list(checks.failures), checks.ROOT
            checks.failures.clear()
            checks.ROOT = Path(tmp)
            try:
                fn()
                return list(checks.failures)
            finally:
                checks.ROOT = real_root
                checks.failures[:] = kept

    def caps(self, added=""):
        return self.run_check(checks._rock_query_caps,
                              {str(QUERY_PATH): FETCHERS + added})


class TestTheCapsCheckCatchesAFourthFetch(CheckTestCase):
    """rock-query-caps — three ways to fetch a collection and no fourth."""

    def test_the_three_fetchers_alone_are_clean(self):
        self.assertEqual(self.caps(), [],
                         "the fetchers are what the check allows")

    def test_a_hand_rolled_cap_is_caught(self):
        found = self.caps('''
def cmd_things(client):
    return client.get(f"Groups/{1}", params={"$top": 20})
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("$top", found[0])
        self.assertIn("cmd_things", found[0], "the message has to name the function")

    def test_an_unbounded_table_read_is_caught(self):
        found = self.caps('''
def cmd_things(client):
    return client.get("Groups", params={"$filter": "Name eq 'x'"})
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("Groups", found[0])

    def test_a_differently_named_client_does_not_evade_it(self):
        found = self.caps('''
def cmd_things(c):
    return c.get("Groups", params={"$filter": "Name eq 'x'"})
''')
        self.assertEqual(len(found), 1, found)

    def test_a_fetch_of_one_row_by_id_is_allowed(self):
        self.assertEqual(self.caps('''
def cmd_thing(client, thing_id):
    return client.get(f"Groups/{thing_id}", params={"$select": "Name"})
'''), [])

    def test_a_dict_lookup_that_happens_to_be_named_get_is_not_a_fetch(self):
        self.assertEqual(self.caps('''
def show(row):
    return row.get("Description"), row.get("GroupTypeId", 0)
'''), [])

    def test_a_nested_function_is_attributed_to_itself(self):
        found = self.caps('''
def cmd_things(client):
    def inner():
        return client.get("Groups", params={"$filter": "x"})
    return inner()
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("inner", found[0])

    def test_deleting_a_fetcher_fails_rather_than_disarming_the_check(self):
        found = self.run_check(
            checks._rock_query_caps,
            {str(QUERY_PATH): FETCHERS.replace("def first(", "def probe(")})
        self.assertTrue(any("first" in f for f in found),
                        f"a renamed fetcher must be reported, got {found}")

    def test_moving_the_file_fails_rather_than_passing_vacuously(self):
        found = self.run_check(checks._rock_query_caps, {})
        self.assertEqual(len(found), 1, found)
        self.assertIn("missing", found[0])

    def test_the_repository_itself_passes(self):
        found = self.run_check(
            checks._rock_query_caps,
            {str(QUERY_PATH): (ROOT / QUERY_PATH).read_text()})
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
