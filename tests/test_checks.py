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
import json
import subprocess
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

    def run_check(self, fn, files, listed=None):
        """Report what `fn` complains about, given `files` as the whole repo.

        The temp directory is made a real git repository with `files` added to
        its index, because the checks ask git what the repository ships rather
        than walking the filesystem. That is also the only way to write a test
        for a file git ignores: put it in `.gitignore` here and it is ignored
        here too, by the same code that ignores it upstairs.

        `listed` stands in for the marketplace catalog, for the checks that walk
        it. Pass plugin names mapped to their marketplace entry.
        """
        with tempfile.TemporaryDirectory() as tmp:
            for rel, source in files.items():
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            for command in (["init", "-q"], ["add", "-A"]):
                subprocess.run(["git", "-C", tmp, *command],
                               check=True, capture_output=True)
            kept, real_root = list(checks.failures), checks.ROOT
            real_listed = checks.LISTED
            checks.failures.clear()
            checks.ROOT = Path(tmp)
            checks.PLUGINS = checks.ROOT / "plugins"
            if listed is not None:
                checks.LISTED = listed
            checks.reset_caches()
            try:
                fn()
                return list(checks.failures)
            finally:
                checks.ROOT = real_root
                checks.PLUGINS = real_root / "plugins"
                checks.LISTED = real_listed
                checks.failures[:] = kept
                checks.reset_caches()

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


class TestTheListingCheckCatchesADriftingColumn(CheckTestCase):
    """rock-listing-rows — the id column is decided in one function."""

    ROW = '''
ID_WIDTH = 6


def row(entity_id, label, indent=2):
    return f"{' ' * indent}{entity_id:{ID_WIDTH}d}  {label}"
'''

    def rows(self, added=""):
        return self.run_check(checks._rock_listing_rows,
                              {str(QUERY_PATH): self.ROW + added})

    def test_the_one_formatter_alone_is_clean(self):
        self.assertEqual(self.rows(), [])

    def test_a_hand_padded_id_is_caught(self):
        found = self.rows('''
def cmd_things(rows):
    for r in rows:
        print(f"  {r['Id']:5d}  {r['Name']}")
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("cmd_things", found[0])

    def test_an_id_in_prose_is_left_alone(self):
        self.assertEqual(self.rows('''
def cmd_thing(gt):
    print(f"  Group Type: {gt['Name']} (ID: {gt['Id']})")
'''), [])

    def test_another_padded_column_is_not_an_id(self):
        self.assertEqual(self.rows('''
def cmd_summary(counts):
    for etype, count in counts.items():
        print(f"  {count:4d}  {etype}")
'''), [])

    def test_deleting_the_formatter_fails_rather_than_disarming_the_check(self):
        found = self.run_check(checks._rock_listing_rows,
                               {str(QUERY_PATH): "x = 1\n"})
        self.assertTrue(any("row()" in f for f in found), found)

    def test_moving_the_file_fails_rather_than_passing_vacuously(self):
        found = self.run_check(checks._rock_listing_rows, {})
        self.assertEqual(len(found), 1, found)
        self.assertIn("missing", found[0])

    def test_the_repository_itself_passes(self):
        found = self.run_check(
            checks._rock_listing_rows,
            {str(QUERY_PATH): (ROOT / QUERY_PATH).read_text()})
        self.assertEqual(found, [])


class TestProvenanceReadsTheFileLists(CheckTestCase):
    """provenance — every shipped file is named in docs/vendored.json."""

    def vendored(self, files):
        return json.dumps({
            "skills": {"rock": {"plugin": "rock", "upstream": "somewhere",
                                "files": files}},
            "runtime": {"files": {}},
        })

    def repo(self, listed, on_disk, extra=None):
        """A one-skill repository, and what its entry claims to cover."""
        files = {"docs/vendored.json": self.vendored(listed)}
        for name in on_disk:
            files[f"plugins/rock/skills/rock/{name}"] = "body\n"
        files.update(extra or {})
        return self.run_check(checks._provenance, files)

    def test_a_list_that_matches_disk_is_clean(self):
        self.assertEqual(self.repo(["SKILL.md", "references/lava.md"],
                                   ["SKILL.md", "references/lava.md"]), [])

    def test_a_shipped_file_nobody_recorded_is_caught(self):
        found = self.repo(["SKILL.md"], ["SKILL.md", "references/lava.md"])
        self.assertEqual(len(found), 1, found)
        self.assertIn("references/lava.md", found[0])
        self.assertIn("where it came from", found[0])

    def test_a_recorded_file_that_is_gone_is_caught(self):
        found = self.repo(["SKILL.md", "references/gone.md"], ["SKILL.md"])
        self.assertEqual(len(found), 1, found)
        self.assertIn("no longer ships", found[0])

    def test_a_file_git_ignores_is_not_a_missing_entry(self):
        self.assertEqual(self.repo(
            ["SKILL.md"], ["SKILL.md"],
            extra={".gitignore": "__pycache__/\n",
                   "plugins/rock/skills/rock/__pycache__/x.pyc": "junk\n"}), [])

    def test_the_runtime_list_is_read_too(self):
        found = self.run_check(checks._provenance, {
            "docs/vendored.json": json.dumps({"skills": {}, "runtime": {
                "files": {"plugins/rock/runtime/scripts/gone.py": "patched"}}}),
            "plugins/rock/runtime/scripts/rock_client.py": "x = 1\n",
        })
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("gone.py" in f and "no longer ships" in f for f in found), found)
        self.assertTrue(any("rock_client.py" in f for f in found), found)

    def test_the_repository_itself_passes(self):
        """Not a repository of our making — this one, and its 54 filenames."""
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._provenance()
            self.assertEqual(list(checks.failures), [])
        finally:
            checks.failures[:] = kept


class TestSkillPathsFollowsThePointers(CheckTestCase):
    """skill-paths — a skill's own files are reachable from the words for them."""

    SKILL = "plugins/dev/skills/probe/SKILL.md"

    def skill(self, body, **extra):
        files = {self.SKILL: body}
        files.update(extra)
        return self.run_check(checks._skill_paths, files)

    def test_a_skill_that_names_what_it_ships_is_clean(self):
        self.assertEqual(self.skill(
            "Read [NOTES.md](NOTES.md) and `references/deep.md`.\n",
            **{"plugins/dev/skills/probe/NOTES.md": "notes\n",
               "plugins/dev/skills/probe/references/deep.md": "deep\n"}), [])

    def test_a_link_to_a_renamed_sidecar_is_caught(self):
        found = self.skill("Read [NOTES.md](NOTES.md) and NOTES-v2.md.\n",
                           **{"plugins/dev/skills/probe/NOTES-v2.md": "body\n"})
        self.assertEqual(len(found), 1, found)
        self.assertIn("links to `NOTES.md`", found[0])

    def test_a_sidecar_that_only_names_itself_is_still_unreachable(self):
        found = self.skill("Nothing to see.\n",
                           **{"plugins/dev/skills/probe/ALONE.md": "ALONE.md is this file.\n"})
        self.assertEqual(len(found), 1, found)
        self.assertIn("ALONE.md", found[0])

    def test_a_sidecar_nothing_names_is_caught(self):
        found = self.skill("Nothing to see.\n",
                           **{"plugins/dev/skills/probe/ORPHAN.md": "body\n"})
        self.assertEqual(len(found), 1, found)
        self.assertIn("ORPHAN.md", found[0])
        self.assertIn("pointer", found[0])

    def test_a_script_named_by_a_relative_path_is_caught(self):
        found = self.skill("Run `scripts/run.py` on the file.\n",
                           **{"plugins/dev/skills/probe/scripts/run.py": "x = 1\n"})
        self.assertEqual(len(found), 1, found)
        self.assertIn("CLAUDE_PLUGIN_ROOT", found[0])

    def test_the_plugin_root_form_is_what_it_asks_for(self):
        self.assertEqual(self.skill(
            'Run `${CLAUDE_PLUGIN_ROOT}/skills/probe/scripts/run.py`.\n',
            **{"plugins/dev/skills/probe/scripts/run.py": "x = 1\n"}), [])

    def test_a_plugin_root_path_into_thin_air_is_caught(self):
        found = self.skill(
            'Run `${CLAUDE_PLUGIN_ROOT}/skills/probe/scripts/gone.py`.\n',
            **{"plugins/dev/skills/probe/scripts/run.py": "x = 1\n"})
        self.assertTrue(any("does not ship" in f for f in found), found)

    def test_an_example_of_somebody_elses_layout_is_left_alone(self):
        self.assertEqual(self.skill(
            "One per context: [./src/ordering/CONTEXT.md](./src/ordering/CONTEXT.md), "
            "and a hole in a template: [Title](url).\n"), [])

    def test_the_repository_itself_passes(self):
        """Not a repository of our making — this one, and its ten sidecar links."""
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._skill_paths()
            self.assertEqual(list(checks.failures), [])
        finally:
            checks.failures[:] = kept


class TestWhichFilesTheChecksSee(CheckTestCase):
    """repo_files — what git tracks, and only what is there to read."""

    def files(self, tree, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            for rel, source in tree.items():
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            for command in (["init", "-q"], ["add", "-A"]):
                subprocess.run(["git", "-C", tmp, *command],
                               check=True, capture_output=True)
            real_root, checks.ROOT = checks.ROOT, Path(tmp)
            try:
                return [str(p.relative_to(tmp))
                        for p in checks.repo_files(**kwargs)], Path(tmp)
            finally:
                checks.ROOT = real_root

    def test_a_prefix_and_a_suffix_narrow_it(self):
        found, _ = self.files(
            {"plugins/a/x.py": "1\n", "plugins/a/x.sh": "1\n", "docs/y.py": "1\n"},
            under="plugins/", suffixes={".py"})
        self.assertEqual(found, ["plugins/a/x.py"])

    def test_what_git_ignores_is_not_a_file_of_ours(self):
        found, _ = self.files({".gitignore": "*.log\n", "keep.md": "1\n",
                               "noise.log": "1\n"})
        self.assertEqual(found, [".gitignore", "keep.md"])

    def test_a_deletion_not_yet_staged_is_dropped_rather_than_returned(self):
        """The index still names it. Every caller opens what it is handed."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gone.md").write_text("body\n")
            for command in (["init", "-q"], ["add", "-A"]):
                subprocess.run(["git", "-C", tmp, *command],
                               check=True, capture_output=True)
            (Path(tmp) / "gone.md").unlink()
            real_root, checks.ROOT = checks.ROOT, Path(tmp)
            try:
                self.assertEqual(checks.repo_files(), [])
            finally:
                checks.ROOT = real_root


class TestWhatAPluginInstalls(CheckTestCase):
    """installs — the closure a department pulls in, and the cycles in the way.

    Two functions used to walk this graph. `dependencies` reported a cycle and
    `cross-references` stopped at one without a word, so a cycle could break the
    closure a department was checked against and only the other check would say.
    """

    def repo(self, deps):
        return {f"plugins/{name}/.claude-plugin/plugin.json":
                json.dumps({"name": name, "description": name,
                            "dependencies": on})
                for name, on in deps.items()}

    def closure(self, deps, of):
        got = {}
        self.run_check(lambda: got.update(reached=checks.installs(of),
                                          cycles=list(checks.DEPENDENCY_CYCLES)),
                       self.repo(deps), listed={n: {} for n in deps})
        return got

    def test_a_plugin_installs_itself_and_everything_below_it(self):
        got = self.closure({"dept": ["dev"], "dev": ["general"], "general": []},
                           of="dept")
        self.assertEqual(got["reached"], {"dept", "dev", "general"})

    def test_a_dependency_off_the_catalog_is_not_walked_into(self):
        """`dependencies` reports that separately. Walking it would crash here."""
        got = self.closure({"dept": ["ghost"]}, of="dept")
        self.assertEqual(got["reached"], {"dept"})

    def test_a_cycle_is_recorded_rather_than_looped_on(self):
        got = self.closure({"dev": ["plan"], "plan": ["dev"]}, of="dev")
        self.assertEqual(got["cycles"], ["dev -> plan -> dev"])
        self.assertEqual(got["reached"], {"dev", "plan"})

    def test_the_cycle_reported_is_the_cycle_and_not_the_path_to_it(self):
        """Reaching a cycle from three plugins away is still that cycle."""
        got = self.closure({"dept": ["dev"], "dev": ["plan"], "plan": ["dev"]},
                           of="dept")
        self.assertEqual(got["cycles"], ["dev -> plan -> dev"])

    def test_the_repository_installs_what_the_dependencies_check_says(self):
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._dependencies()
            self.assertEqual(checks.failures, [])
        finally:
            checks.failures[:] = kept


class TestWhoOwnsAFile(CheckTestCase):
    """owner_of — the plugin and the skill, read out of a path in one place.

    Five call sites decoded this themselves, three counting from the end of the
    path and two from the front, and two of them called different halves of it
    the owner.
    """

    def owner(self, rel):
        return checks.owner_of(checks.PLUGINS / rel)

    def test_a_file_in_a_skill_names_both(self):
        self.assertEqual(self.owner("general/skills/to-ste/SKILL.md"),
                         ("general", "to-ste"))

    def test_a_file_deeper_in_a_skill_still_names_both(self):
        self.assertEqual(self.owner("general/skills/to-ste/scripts/lint.py"),
                         ("general", "to-ste"))

    def test_a_file_in_no_skill_has_no_skill(self):
        self.assertEqual(self.owner("dev/.claude-plugin/plugin.json"),
                         ("dev", None))
        self.assertEqual(self.owner("rock/runtime/scripts/rock_client.py"),
                         ("rock", None))

    def test_the_skills_directory_itself_owns_nothing(self):
        """`plugins/dev/skills` is three parts, and a skill needs a file in it."""
        self.assertEqual(self.owner("dev/skills"), ("dev", None))


if __name__ == "__main__":
    unittest.main()
