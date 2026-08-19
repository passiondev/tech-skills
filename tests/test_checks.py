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

    def run_check(self, fn, files, listed=None, skills=None):
        """Report what `fn` complains about, given `files` as the whole repo.

        The temp directory is made a real git repository with `files` added to
        its index, because the checks ask git what the repository ships rather
        than walking the filesystem. That is also the only way to write a test
        for a file git ignores: put it in `.gitignore` here and it is ignored
        here too, by the same code that ignores it upstairs.

        `listed` stands in for the marketplace catalog and `skills` for the
        SKILL.md files on disk, for the checks that read them. Both are computed
        once at import against the real repository, so a fixture has to say what
        it holds instead.
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
            real_listed, real_skills = checks.LISTED, checks.SKILLS
            checks.failures.clear()
            checks.ROOT = Path(tmp)
            checks.PLUGINS = checks.ROOT / "plugins"
            if listed is not None:
                checks.LISTED = listed
            if skills is not None:
                checks.SKILLS = [checks.PLUGINS / rel for rel in skills]
            checks.reset_caches()
            try:
                fn()
                return list(checks.failures)
            finally:
                checks.ROOT = real_root
                checks.PLUGINS = real_root / "plugins"
                checks.LISTED, checks.SKILLS = real_listed, real_skills
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


class TestTheReadViewCheckCatchesACommandThatPrints(CheckTestCase):
    """rock-read-views — a read command returns its answer, `render` prints it."""

    BASE = '''
import sys


def render(report):
    print(report)


def cmd_block_set(args, client):
    print("  set")


def cmd_person_create(args, client):
    print("  created")


def cmd_person_update(args, client):
    print("  updated")


def cmd_exception_clear(args, client):
    print("  cleared")


def cmd_search(args, client):
    print("Searching Groups...")
'''

    def views(self, added=""):
        return self.run_check(checks._rock_read_views,
                              {str(QUERY_PATH): self.BASE + added})

    def test_the_writers_that_report_as_they_go_are_clean(self):
        self.assertEqual(self.views(), [])

    def test_a_read_view_that_prints_is_caught(self):
        found = self.views('''
def cmd_group(args, client):
    print(client.get("Groups/1")["Name"])
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("cmd_group", found[0])
        self.assertIn("render()", found[0])

    def test_a_read_view_that_returns_a_renderable_is_clean(self):
        self.assertEqual(self.views('''
def cmd_group(args, client):
    detail = Detail("Ushers (ID: 7)")
    detail.field("Campus", "Downtown")
    return detail
'''), [])

    def test_a_print_hidden_in_a_nested_helper_is_caught(self):
        """The dodge, and the accident: a `def` inside the view that prints.

        `_by_function` tags a node with the innermost function around it, so a
        nested one would come back tagged with its own name and pass.
        """
        found = self.views('''
def cmd_group(args, client):
    def emit(line):
        print(line)
    emit("Ushers")
''')
        self.assertEqual(len(found), 1, found)
        self.assertIn("cmd_group", found[0])

    def test_writing_to_stdout_by_hand_is_the_same_offence(self):
        found = self.views('''
def cmd_group(args, client):
    sys.stdout.write("Ushers")
''')
        self.assertEqual(len(found), 1, found)

    def test_a_print_aimed_at_stdout_by_name_is_still_a_print(self):
        found = self.views('''
def cmd_group(args, client):
    print("Ushers", file=sys.stdout)
''')
        self.assertEqual(len(found), 1, found)

    def test_a_warning_on_stderr_is_not_the_answer(self):
        """Nothing reading the answer sees stderr, so a view may still warn."""
        self.assertEqual(self.views('''
def cmd_group(args, client):
    print("Warning: settings unreadable", file=sys.stderr)
    return Detail("Ushers (ID: 7)")
'''), [])

    def test_a_helper_a_view_calls_is_out_of_this_checks_reach(self):
        """`_find_entity` asks which of several matches was meant, on stdout.

        This reads command bodies, so a helper they call sits outside it. Worth
        a test rather than a docstring line, because a check read as broader
        than it is, is worse than one that admits its edge.
        """
        self.assertEqual(self.views('''
def _find_entity(client, entity, identifier):
    print("Multiple matches:")
'''), [])

    def test_deleting_the_renderer_fails_rather_than_disarming_the_check(self):
        found = self.run_check(
            checks._rock_read_views,
            {str(QUERY_PATH): "def cmd_group(args, client):\n    pass\n"})
        self.assertTrue(any("render()" in f for f in found), found)

    def test_an_allow_list_entry_that_no_longer_exists_is_caught(self):
        """A renamed write command has to be renamed here too.

        Left alone, the entry sits there covering whatever takes the name next.
        """
        source = self.BASE.replace("def cmd_person_update", "def cmd_person_edit")
        found = self.run_check(checks._rock_read_views, {str(QUERY_PATH): source})
        self.assertEqual(len(found), 2, found)
        self.assertIn("allow-list", found[0])
        self.assertIn("cmd_person_update", found[0])
        # The rename lands the write command outside the list, so it is reported
        # as a view that prints. Both halves are the same message: the list and
        # the commands have to be renamed together.
        self.assertIn("cmd_person_edit", found[1])

    def test_moving_the_file_fails_rather_than_passing_vacuously(self):
        found = self.run_check(checks._rock_read_views, {})
        self.assertEqual(len(found), 1, found)
        self.assertIn("missing", found[0])

    def test_the_repository_itself_passes(self):
        found = self.run_check(
            checks._rock_read_views,
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
        # `runtime` is keyed by plugin. Empty here: this fixture ships no runtime
        # directory, and an entry for one that is absent is its own failure.
        return json.dumps({
            "skills": {"rock": {"plugin": "rock", "upstream": "somewhere",
                                "files": files}},
            "runtime": {},
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
            "docs/vendored.json": json.dumps({"skills": {}, "runtime": {"rock": {
                "files": {"plugins/rock/runtime/scripts/gone.py": "patched"}}}}),
            "plugins/rock/runtime/scripts/rock_client.py": "x = 1\n",
        })
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("gone.py" in f and "no longer ships" in f for f in found), found)
        self.assertTrue(any("rock_client.py" in f for f in found), found)

    def test_every_plugin_runtime_is_read_not_only_rocks(self):
        """The check went to a hardcoded plugins/rock/runtime/, so jira's
        arrived as a directory of shipped code that no list named."""
        found = self.run_check(checks._provenance, {
            "docs/vendored.json": json.dumps({"skills": {}, "runtime": {"rock": {
                "files": {"plugins/rock/runtime/scripts/rock_client.py": "patched"}}}}),
            "plugins/rock/runtime/scripts/rock_client.py": "x = 1\n",
            "plugins/jira/runtime/scripts/jira_client.py": "x = 1\n",
        })
        self.assertEqual(len(found), 1, found)
        self.assertIn("no entry for `jira`", found[0])

    def test_a_runtime_entry_for_a_plugin_with_no_runtime_is_stale(self):
        found = self.run_check(checks._provenance, {
            "docs/vendored.json": json.dumps({"skills": {}, "runtime": {
                "rock": {"files": {}}}}),
            "plugins/rock/skills/rock/SKILL.md": "body\n",
        })
        self.assertTrue(any("names `rock`" in f and "no runtime" in f
                            for f in found), found)

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


class TestTheCredentialLoaderEveryPluginCarries(CheckTestCase):
    """passion_env — one copy per plugin, byte-identical, and no second one.

    The check counted copies in total and passed on "two or more", so it read
    jira's two — one per skill, because a skill's scripts directory was the only
    place its own scripts could import from — as the floor rather than as a copy
    somebody made. ADR 0004 argues against copies and against this check; what
    makes it earn its place is counting per plugin, since `${CLAUDE_PLUGIN_ROOT}`
    forces exactly one per plugin and excuses nothing beyond that.
    """

    BODY = "ENV_FILE = 1\n"

    def repo(self, *paths, drift=()):
        files = {rel: (self.BODY + "# changed\n" if rel in drift else self.BODY)
                 for rel in paths}
        return self.run_check(checks._passion_env, files)

    def test_one_copy_per_plugin_passes(self):
        self.assertEqual(self.repo("plugins/rock/runtime/scripts/passion_env.py",
                                   "plugins/jira/runtime/scripts/passion_env.py"), [])

    def test_a_single_plugin_with_a_single_copy_passes(self):
        """Two was never the point. One plugin needing credentials needs one."""
        self.assertEqual(
            self.repo("plugins/rock/runtime/scripts/passion_env.py"), [])

    def test_a_second_copy_inside_one_plugin_is_caught(self):
        found = self.repo("plugins/jira/skills/ticket/scripts/passion_env.py",
                          "plugins/jira/skills/sprint/scripts/passion_env.py")
        self.assertEqual(len(found), 1, found)
        self.assertIn("`jira` ships 2 copies", found[0])
        self.assertIn("skills/ticket", found[0], "say which files")

    def test_copies_that_have_drifted_are_caught(self):
        found = self.repo("plugins/rock/runtime/scripts/passion_env.py",
                          "plugins/jira/runtime/scripts/passion_env.py",
                          drift=("plugins/jira/runtime/scripts/passion_env.py",))
        self.assertEqual(len(found), 1, found)
        self.assertIn("drifted apart", found[0])

    def test_shipping_none_at_all_is_caught(self):
        found = self.repo("plugins/rock/runtime/scripts/rock_client.py")
        self.assertEqual(len(found), 1, found)
        self.assertIn("nothing ships", found[0])

    def test_the_repository_itself_passes(self):
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._passion_env()
            self.assertEqual(checks.failures, [])
        finally:
            checks.failures[:] = kept


SETTINGS = {"extraKnownMarketplaces": {"passion-tech": {
    "source": {"source": "github", "repo": "passiondev/tech-skills"},
    "autoUpdate": True}}}


class TestTheOnboardingBlockPeoplePasteFrom(CheckTestCase):
    """onboarding — the settings a reader copies into their own settings.json.

    Nobody types this from memory, so a wrong block is a wrong install for
    everyone who reads the file next. This check ran as inline Python in the
    workflow, where nobody could run it locally and it stopped at the first
    thing it found.
    """

    def onboarding(self, block, before="Paste this:\n\n"):
        text = f"# Onboarding\n\n{before}```json\n{block}\n```\n"
        return self.run_check(checks._onboarding, {"ONBOARDING.md": text})

    def test_the_block_we_ship_passes(self):
        self.assertEqual(self.onboarding(json.dumps(SETTINGS, indent=2)), [])

    def test_a_document_with_no_block_is_a_document_nobody_can_follow(self):
        found = self.run_check(checks._onboarding,
                               {"ONBOARDING.md": "# Onboarding\n\nGood luck.\n"})
        self.assertEqual(len(found), 1)
        self.assertIn("no JSON block", found[0])

    def test_a_block_that_does_not_parse_is_reported_with_the_reason(self):
        found = self.onboarding('{"extraKnownMarketplaces": }')
        self.assertEqual(len(found), 1)
        self.assertIn("not valid JSON", found[0])

    def test_a_hand_written_enabledPlugins_is_the_bug_adr_0012_measured(self):
        broken = {**SETTINGS, "enabledPlugins": {"ops@passion-tech": True}}
        found = self.onboarding(json.dumps(broken))
        self.assertEqual(len(found), 1)
        self.assertIn("enabledPlugins", found[0])

    def test_autoupdate_off_is_a_fix_that_reaches_nobody(self):
        settings = json.loads(json.dumps(SETTINGS))
        settings["extraKnownMarketplaces"]["passion-tech"]["autoUpdate"] = False
        found = self.onboarding(json.dumps(settings))
        self.assertEqual(len(found), 1)
        self.assertIn("autoUpdate", found[0])

    def test_a_missing_marketplace_entry_leaves_the_install_nothing_to_read(self):
        found = self.onboarding(json.dumps({"extraKnownMarketplaces": {}}))
        self.assertEqual(len(found), 1)
        self.assertIn("passion-tech", found[0])

    def test_the_wrong_repo_is_named_in_the_complaint(self):
        settings = json.loads(json.dumps(SETTINGS))
        settings["extraKnownMarketplaces"]["passion-tech"]["source"]["repo"] = "someone/else"
        found = self.onboarding(json.dumps(settings))
        self.assertEqual(len(found), 1)
        self.assertIn("someone/else", found[0])

    def test_every_block_in_the_document_is_parsed_not_only_the_first(self):
        text = ("# Onboarding\n\n```json\n" + json.dumps(SETTINGS)
                + "\n```\n\nand then\n\n```json\n{oops}\n```\n")
        found = self.run_check(checks._onboarding, {"ONBOARDING.md": text})
        self.assertEqual(len(found), 1)
        self.assertIn("block 2", found[0])

    def test_the_document_we_ship_passes(self):
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._onboarding()
            self.assertEqual(checks.failures, [])
        finally:
            checks.failures[:] = kept


class TestTheReadmeNamesEverythingOnOffer(CheckTestCase):
    """readme — a bundle nobody can find is a bundle nobody installs.

    Same for a skill left out of the roster. The names come from the marketplace
    and from disk. The department half of this check ran as a regex holding the
    five names it was checking, so a sixth would have failed it for the wrong
    reason.
    """

    LISTED = {"ops": {"category": "department"},
              "finance": {"category": "department"},
              "general": {"category": "general"},
              "jira": {"category": "general"}}
    SKILLS = ["general/skills/teach/SKILL.md", "general/skills/research/SKILL.md",
              "jira/skills/ticket/SKILL.md"]
    ROSTER = ("**general** — thinking: `teach`, `research`\n"
              "**jira** — `ticket`\n")

    def readme(self, body):
        return self.run_check(checks._readme, {"README.md": body},
                              listed=self.LISTED, skills=self.SKILLS)

    def roster(self, roster):
        """A README saying everything right except what `roster` says."""
        return self.readme(f"Install `ops` or `finance`.\n\n{roster}")

    def test_both_bundles_and_the_whole_roster_passes(self):
        self.assertEqual(self.readme(f"Install `ops` or `finance`.\n\n{self.ROSTER}"), [])

    def test_a_bundle_the_prose_never_names_is_reported(self):
        found = self.readme(f"Install `ops`.\n\n{self.ROSTER}")
        self.assertEqual(len(found), 1)
        self.assertIn("`finance`", found[0])

    def test_a_name_in_prose_without_a_code_span_does_not_count(self):
        """The README names bundles as commands, and a bare word is not one."""
        found = self.readme(f"Install ops or finance.\n\n{self.ROSTER}")
        self.assertEqual(len(found), 2)

    def test_a_roster_that_forgets_a_skill_hides_it(self):
        found = self.roster(self.ROSTER.replace(", `research`", ""))
        self.assertEqual(len(found), 1)
        self.assertIn("does not name `research`, which `general` ships", found[0])

    def test_a_roster_naming_a_skill_that_is_gone(self):
        found = self.roster(self.ROSTER.replace("`ticket`", "`ticket`, `retired`"))
        self.assertEqual(len(found), 1)
        self.assertIn("names `retired` under `jira`", found[0])

    def test_a_capability_plugin_with_no_roster_line_at_all(self):
        found = self.roster(self.ROSTER.replace("**jira** — `ticket`\n", ""))
        self.assertEqual(len(found), 1)
        self.assertIn("never lists what `jira` holds", found[0])

    def test_a_roster_line_for_a_plugin_the_marketplace_dropped(self):
        found = self.roster(self.ROSTER.replace("**jira**", "**gone**"))
        self.assertEqual(len(found), 2)
        self.assertIn("does not offer as a capability plugin", found[0])
        self.assertIn("never lists what `jira` holds", found[1])

    def test_a_roster_entry_wrapped_over_two_lines_is_read_whole(self):
        self.assertEqual(
            self.roster(self.ROSTER.replace("`teach`, `research`", "`teach`,\n`research`")),
            [])

    def test_the_readme_we_ship_passes(self):
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._readme()
            self.assertEqual(checks.failures, [])
        finally:
            checks.failures[:] = kept


class TestEveryNumberTheReadmeStates(CheckTestCase):
    """readme-counts — eight hand-maintained numbers, each stale on the next skill.

    A number in a README reads as a fact rather than as a claim, so a wrong one
    misinforms instead of confusing. Every one of these was right when somebody
    typed it.
    """

    LISTED = {"ops": {"category": "department"},
              "general": {"category": "general"},
              "jira": {"category": "general"}}
    SKILLS = ["general/skills/teach/SKILL.md", "general/skills/research/SKILL.md",
              "jira/skills/ticket/SKILL.md"]
    VENDORED = {"skills": {
        "teach": {"plugin": "general", "upstream": "mattpocock/skills"},
        "research": {"plugin": "general", "upstream": "mattpocock/skills"},
        "ticket": {"plugin": "jira", "upstream": "passion-original"}}}

    def readme(self, body, adrs=2):
        files = {"README.md": body,
                 "docs/vendored.json": json.dumps(self.VENDORED),
                 "plugins/ops/.claude-plugin/plugin.json": json.dumps(
                     {"name": "ops", "dependencies": ["general", "jira"]}),
                 "plugins/general/.claude-plugin/plugin.json": json.dumps({"name": "general"}),
                 "plugins/jira/.claude-plugin/plugin.json": json.dumps({"name": "jira"})}
        for i in range(1, adrs + 1):
            files[f"docs/adr/{i:04d}-a-decision.md"] = "# A decision\n"
        for rel in self.SKILLS:
            files[f"plugins/{rel}"] = "---\nname: x\n---\n"
        return self.run_check(checks._readme_counts, files,
                              listed=self.LISTED, skills=self.SKILLS)

    TRUE = ("| `ops` | 3 | general, jira |\n"
            "\nTwo decisions and their reasoning are in docs/adr/.\n"
            "\ntwo of the three skills are Matt Pocock's work.\n")

    def test_a_readme_telling_the_truth_passes(self):
        self.assertEqual(self.readme(self.TRUE), [])

    def test_a_bundle_row_counting_wrong_is_told_the_real_number(self):
        found = self.readme(self.TRUE.replace("| 3 |", "| 7 |"))
        self.assertEqual(len(found), 1)
        self.assertIn("says `ops` has 7 skills. It installs 3", found[0])

    def test_a_bundle_row_naming_the_wrong_plugins_is_told_which(self):
        found = self.readme(self.TRUE.replace("general, jira", "general, dev"))
        self.assertEqual(len(found), 1)
        self.assertIn("lists general, dev for `ops`", found[0])

    def test_a_row_for_a_plugin_the_marketplace_dropped(self):
        found = self.readme(self.TRUE.replace("`ops`", "`gone`"))
        self.assertEqual(len(found), 1)
        self.assertIn("not a plugin the marketplace lists", found[0])

    def test_a_missing_row_is_a_bundle_the_table_forgot(self):
        found = self.readme(self.TRUE.replace("| `ops` | 3 | general, jira |\n", ""))
        self.assertEqual(len(found), 1)
        self.assertIn("a row was added or lost", found[0])

    def test_the_count_of_decisions_is_read_as_a_word(self):
        found = self.readme(self.TRUE, adrs=5)
        self.assertEqual(len(found), 1)
        self.assertIn("says Two decisions. docs/adr holds 5 — five", found[0])

    def test_a_capitalised_number_at_the_start_of_a_sentence_still_counts(self):
        """The README writes `Twenty-three decisions`, mid-paragraph or not."""
        self.assertEqual(self.readme(self.TRUE.replace("Two decisions", "two decisions")), [])

    def test_the_licence_note_carries_two_numbers_and_both_are_checked(self):
        found = self.readme(self.TRUE.replace("two of the three skills",
                                              "nine of the eleven skills"))
        self.assertEqual(len(found), 2)
        self.assertIn("says nine where 2 skills are his — two", found[0])
        self.assertIn("says eleven where 3 skills ship — three", found[1])

    def test_the_licence_note_is_found_across_a_line_break(self):
        wrapped = self.TRUE.replace("two of the three skills are Matt Pocock's work.",
                                    "two of the\nthree skills are Matt Pocock's work.")
        self.assertEqual(self.readme(wrapped), [])

    def test_the_readme_we_ship_passes(self):
        kept = list(checks.failures)
        checks.failures.clear()
        try:
            checks._readme_counts()
            self.assertEqual(checks.failures, [])
        finally:
            checks.failures[:] = kept


class TestSpellingANumberOut(unittest.TestCase):
    """in_words — the README writes its numbers as words, so the check must too."""

    def test_it_spells_the_way_the_readme_spells(self):
        self.assertEqual(
            [checks.in_words(n) for n in (0, 5, 11, 18, 19, 20, 23, 24, 30, 41)],
            ["zero", "five", "eleven", "eighteen", "nineteen", "twenty",
             "twenty-three", "twenty-four", "thirty", "forty-one"])


if __name__ == "__main__":
    unittest.main()
