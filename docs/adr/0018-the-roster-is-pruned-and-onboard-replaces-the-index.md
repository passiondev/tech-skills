# The roster is pruned, Analytics gains plan, and `onboard` replaces the index

Three changes to what ships, made together because they answer the same question — what does a person see when they open the picker, and does any of it help them today.

**`handoff` and `writing-great-skills` are dropped.** Neither is referenced by another skill and neither was asked for. `writing-great-skills` served contributors, and contributing is rare enough that reading the file in the repo beats carrying it in thirty pickers; [0007](0007-what-general-contains.md) admitted it on a thirty-two-token argument, which is a reason it is cheap, not a reason it is useful.

**`grilling` was on the same list and stays.** It is not a leaf. `grill-me` and `grill-with-docs` are one-line skills whose entire body runs a grilling session, and `wayfinder`, `triage`, and `improve-codebase-architecture` all name it. It also cannot be hidden behind `disable-model-invocation: true` to shrink the picker — that flag strips a skill from other skills' reach, not just the model's, which would break the three that depend on it. The visible cost is 26 tokens; the alternative is inlining the same prose into five files.

**Analytics gains `plan`.** [0008](0008-department-to-capability-mapping.md) gave them `dev` on the reasoning that they write queries and transformations, and [0007](0007-what-general-contains.md) kept the ticket-authoring cluster away from them on the reasoning that they do not write specs. Both cannot be true of the same people. Analysts scope work and file tickets like everyone else, and the split was making `/plan:domain-modeling` a dangling pointer from two skills they did have.

**`onboard` is added to `general`.** It asks three questions — role and team, what last week was spent on, what they would hand off — then names two or three skills tied to those answers and stops. The premise is that a twenty-nine-skill list is not an introduction; it is a reason to close the picker.

## Considered options

- **Keep `writing-great-skills` and let `onboard` point at it.** Self-extending marketplace, one hop away. Rejected because `onboard`'s whole design is to name fewer things, and a skill about writing skills is not what anyone's first week needs. The file is still in git history and upstream ships a better version.
- **`onboard` as a README section rather than a skill.** No context cost at all, and the README already lists everything. Rejected because a README lists; it does not ask. The three questions are the mechanism — without them the recommendation is a table again, and [0012](0012-onboarding-runs-through-claude-code.md) already committed to Claude Code doing the walking rather than a document.
- **Give Analytics `plan` by moving `domain-modeling` into `general` instead.** Smaller change, fixes both dangling pointers. Rejected because the pointers were the symptom. `to-spec`, `to-tickets`, and `triage` are as relevant to an analyst as `domain-modeling`, and splitting one skill out of the cluster to dodge a dependency edit leaves the mapping still wrong.

## Consequences

`onboard` names skills from every plugin, including ones its reader may not have installed — the opposite of what [0017](0017-skill-pointers-carry-their-namespace.md) enforces. Eleven `OPTIONAL_REFS` entries would have gutted that list's meaning, so `check.py` gained a separate `CATALOGUE_FILES` exemption that waives only the reachability rule. Bare pointers, unknown skills, and wrong prefixes still fail inside a catalogue, and a stale catalogue entry fails too. If a second catalogue skill ever appears, this is the mechanism; if a third does, the reachability rule is probably wrong.

`onboard`'s recommendation table lists skills by name, so it goes stale when the roster changes. Nothing checks the table's *contents* — CI verifies every skill it names exists and is spelled right, which catches a removal but not an addition that should have been offered. `docs/vendored.json` carries the reminder.

Analytics gaining `plan` retired one of the four cross-boundary caveats from [0017](0017-skill-pointers-carry-their-namespace.md), and the check that noticed is new: an `OPTIONAL_REFS` entry now fails when every department with the referring plugin also installs the target. Three remain, all for Ops or Service and Support.

Per-turn context: Analytics 29 skills, Local Engineering 32, Global Engineering 24, Ops 16, Service and Support 15. Analytics moved the most and is now the second-largest install.
