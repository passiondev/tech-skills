# Jira is assumed, not configured per repo

The five skills that ask for a configured issue tracker stop asking. Jira is the tracker for every repository at Passion, `general` depends on `jira` for every department, so the answer is known before the question is asked. The vendored copies name Jira directly and defer to the `jira` skill for how to reach it. `setup-repo` keeps the parts that genuinely vary per repository — the triage label vocabulary and the documentation layout — and loses Section A.

Upstream cannot make this assumption; it ships to strangers whose tracker it cannot know, so it generates `docs/agents/issue-tracker.md` and has five skills check for it. We are not strangers. Making thirty people run a setup skill in every repository to answer a question with one possible answer is a per-repo tax for no information. This is the divergence [0006](0006-vendored-skills-diverge-on-purpose.md) predicted, and the first concrete instance of it.

It also closes a hole in the mapping. [0008](0008-department-to-capability-mapping.md) gives Analytics `dev` without `plan`, and `code-review` lives in `dev` while `setup-repo` lives in `plan` — so an analyst following `code-review`'s instruction to run `/setup-repo` would be told to run something they do not have. Pointing `code-review` at the `jira` skill instead removes the cross-plugin reference entirely, because `jira` is the one capability every department has.

## Considered options

- **Ship a pre-filled `docs/agents/issue-tracker.md` into every repo.** Keeps the vendored skills byte-identical to upstream, so the diff [0011](0011-upstream-relationship-and-licence.md) wants stays clean. Rejected because it puts the same generated file in every repository at Passion, to be maintained in all of them, when the content is identical everywhere and already exists as a skill.
- **Add `plan` to Analytics.** Fixes the dangling reference by making the referenced skill present. Rejected because it hands `to-spec` and `wayfinder` to people the mapping deliberately kept them from, to solve a documentation problem.
- **Leave the references and let them fail softly.** `wayfinder` already degrades — "if no tracker has been provided, default to the local-markdown tracker." Rejected because that default is wrong here in a way that produces silent bad behaviour: an analyst gets tickets written to `.scratch/` instead of Jira, and nothing announces it.

## Consequences

Six vendored files now differ from upstream on purpose — the five referrers and `setup-repo` itself. Each needs the upstream commit recorded alongside it, which [0011](0011-upstream-relationship-and-licence.md) already required and this makes urgent rather than theoretical.

The skills become wrong the moment any team at Passion tracks work somewhere else. That is the trade: the configuration step existed to absorb exactly that change, and removing it means a tracker migration edits skills instead of answering a prompt.

`setup-repo` is now a smaller skill that may not justify its own existence. It survives on triage labels and doc layout alone, and if [0008](0008-department-to-capability-mapping.md)'s prediction holds and `triage` is the first thing trimmed from `plan`, what remains is one question about where ADRs live.

*It did not justify it. [0019](0019-setup-repo-is-removed.md) deleted the skill — the triage labels turned out to be a table mapping each name to itself, and the doc layout is created lazily by `domain-modeling`. `triage` survived; `setup-repo` did not.*
