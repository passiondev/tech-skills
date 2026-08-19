# One place decides, and a check fails the next copy

Twenty commits deepened the Rock runtime, the Jira scripts and the CI script. Each one found a decision made in several places, where the copies had drifted and nothing could see it. Each one gave that decision a single home and left a check that fails the next copy. The test suite goes from 55 tests to 375, and CI from 14 checks to 22.

This decision supersedes nothing. It records the pattern the pass settled on. The next pass starts there rather than at the same ten bugs.

## What the pass found

No line below was wrong on its own. That is the reason for writing them down.

In the Rock runtime:

- Eighteen loops formatted the id column by hand, and the width had drifted to three: `:5d`, `:6d` and `:8d`.
- Five read commands climbed their own name-or-id ladder, so `attendance --group Ushers` resolved to "Ushers Team" where both existed.
- Nine write sites climbed that ladder four ways, and one raised `KeyError` for a block naming no type, after creating its page.
- Twenty-eight collection fetches went around the two capped fetchers, so one listing printed 100 for a table holding ten times that.
- Twenty-one detail views printed for themselves, each with its own indent, its own guard on every optional line and its own `--json` branch.
- Thirty blocks in `rock_build.py` held the same four lines: try, except, record, return.

In CI, the README and the Jira scripts:

- Five checks each answered for themselves which files this repository ships, and one opened binary blobs out of a linter cache.
- The checks read ten plugin manifests between five and sixteen times each. Two functions disagreed about a cycle in the graph.
- Eighteen numbers and name lists in the README were true when somebody typed them. None had a way to go stale loudly.
- Four Jira scripts each rolled their own curl, and one put the API token in argv, where any local user reads it out of `ps`.

A reviewer reads one of those lines at a time, and each one is defensible. A copy cannot see the other copies from inside itself. So the copies drift, and a review is the one instrument that cannot catch it.

## One place decides

Every fix is the same move: name the decision, give it one home, delete the copies.

- `_find_entity` is the read-side lookup ladder for fourteen commands, and `resolve_ref` is the write-side one for nine.
- `get_capped` and `tally` decide what a bounded fetch says about its bound, and `row` chooses the id column once.
- `step` wraps one request to Rock and records it by name when it fails, and `BuildResult` holds what a plan did.
- `repo_files` asks git which files this repository ships, because a filesystem walk finds whatever the last command left behind.
- `json_at` reads each manifest once, `installs` walks the graph once, and `jira_client.py` is one client for four call sites.

The deletion test kept this honest. Deleting `_find_entity` puts a four-strategy ladder back into fourteen commands, so it concentrates complexity and it stays. Deleting `more_note` moves one sentence back to its only caller, so it went.

## The module that printed

Twenty-nine read commands returned nothing and spoke only through `print`. A test of one had to run the command, capture stdout and match formatted text. That is why there were none.

A command builds a `Listing`, a `Detail`, a `Raw` or a `Text` now and returns it, and `render` at the boundary prints it. The return value is the test surface: a test reads `listing.rows` or `detail.parts` and never sees a column width. The shape came off the write side, where the handlers already recorded into a `BuildResult` for `run_plan` to print.

That is depth through a smaller interface rather than through a bigger implementation. What a read command exposes is one object that renders itself. The indent lives inside the renderable and nowhere else, which is what stops it drifting to three widths again.

## A name that resolves to nothing, and a collection that is empty

The renderables settled a question two earlier commits had left open: the exit code for a lookup that matches nothing. An exit code of 1 for every empty answer is right for `query group "typo"` and wrong for `query workflows` on an instance holding none.

The two cases reach the boundary by separate routes now, so one answer no longer has to cover both. A name that resolves to nothing raises `LookupMiss`, which carries the renderable that says so, and the boundary exits 1. A collection Rock genuinely has none of is a `Listing` with no rows, and exits 0. The skill states what an exit code of 1 means. A lookup that reports its result is not a tool failure.

## The check that fails the next copy

Eight checks are new: `skill-paths`, `rock-query-caps`, `rock-listing-rows`, `rock-read-views`, `rock-build-reports`, `onboarding`, `readme` and `readme-counts`.

A test covers the site it names. The ninth copy lands somewhere no test names. So each fix here ends in a check rather than in tests alone. The four Rock checks state an invariant over a whole module:

- No `$top` outside the three fetchers.
- No id column formatted anywhere but `row`.
- Nothing in `rock_query.py` reaches stdout except `render` and the write commands.
- Nothing in `rock_build.py` reaches stdout except `BuildResult.report` and the three functions that run before the first handler.

Three properties make them worth the weight. Each check reads the parse tree rather than the text, so a docstring naming a dead route stays documentation. Each carries an allow-list by name, so a real exception costs a review conversation rather than a quiet edit. Each fails on an allow-list entry that no longer resolves. A rename visits the list rather than leaving a dead entry to cover its namesake.

`rock-read-views` also fails where a call reaches stdout from somewhere the check does not look. A check that reports nothing reads exactly like a check that passes.

## Considered options

- **Write the rule down in the skill instead.** Cheaper than a check, and this repository documents plenty already. Rejected on evidence from inside the pass. The reference at `references/writing.md` had written one of these bugs down as expected output. A skill that explains why a failure is acceptable is harder to find than the failure. [0022](0022-rock-writes-use-patch-and-one-operation-is-generic.md) names the same shape.

- **Extract pure helpers and cover those.** The usual advice, and it misses every bug here. Each one lived in how a caller called the helper. `attendance --group` had a working ladder available and climbed its own instead. Locality is the property at stake, and a helper nobody calls does not have it.

- **One rewrite of `rock_query.py`.** It is the largest file here, and twenty-nine commands sit in it. Rejected on review capacity rather than on merit. This repository has one reviewer, and a merge is live for thirty people at once, by [0009](0009-no-plugin-versions.md) and [0010](0010-curator-merges-ci-guards.md). Twenty commits, each one green, is twenty things that reviewer can drop one at a time.

- **Tests and no checks.** Half the value at half the cost. Rejected because the bug this pass kept meeting is the copy nobody knew about. A test knows only the sites it names.

- **A tool for this.** Nothing off the shelf answers whether a caller used the shared ladder. The checks are twenty lines of `ast` each, and they answer that.

## Consequences

The runtime files grew. `rock_query.py` went from 1836 lines to 1975, `rock_build.py` from 1452 to 1594, and `check.py` from 635 to 1415. Depth is a property of the interface rather than of the line count. Every one of these modules is smaller to a caller than before. A reader who expects a deepening pass to shrink the files will not find that here.

The suite runs 375 tests in two seconds and touches no network. That is what makes the checks affordable: both run on every commit, so a copy has one commit to live.

Eight allow-lists are eight lists that go stale. Each one fails on its own stale entry, which is the best answer available. The structure is still not free. A ninth check that wants an allow-list should first ask whether the invariant holds without one.

Three changes reach an operator. A lookup that matches nothing exits 1. A plan naming a category or a form field Rock cannot place fails rather than warns. A capped collection reports the cap in place of a total. A count of 100 no longer reads as a whole table.

The README now says twenty-four decisions, and `readme-counts` fails the next ADR that lands without touching it. This ADR is the first one that check counts.

One thing the pass did not do. The file `rock_query.py` is still the largest in this repository, and it still holds twenty-nine commands behind one argument parser. The renderables make each command small, so the file is long rather than deep. To split it is a separate decision with a separate cost.

The tests for the six new write operations run against a fake client. What they pin is the shape of each request rather than what Rock does with it.
