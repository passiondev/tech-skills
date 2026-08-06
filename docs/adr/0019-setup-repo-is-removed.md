# `setup-repo` is removed; `codebase-design` stays

`setup-repo` is deleted. It was the last skill whose job was configuring a repository before the others would work, and two earlier decisions had already taken its reasons away.

[0015](0015-jira-is-assumed-not-configured.md) removed Section A once Jira became a given for every department, and predicted the rest: *"`setup-repo` is now a smaller skill that may not justify its own existence."* What survived was two things. The triage label mapping in `triage-labels.md` was a five-row table whose left and right columns were **identical** — a placeholder nobody had edited, sitting behind a run-once ritual. And the domain doc layout, which `domain-modeling` already creates lazily when the first term or decision lands, by its own instruction.

So the three skills that told people to run it — `to-spec`, `to-tickets`, `triage` — were pointing at a configuration step that configured a table already correct by default and a directory another skill makes on demand. They now state the five canonical roles directly and say to read the project's existing labels and ask if the mapping is not obvious, which is what a person would have done anyway.

`codebase-design` was considered alongside it and kept. The premise for cutting it was that it looked per-repo like `setup-repo`; it is not. It is Ousterhout's deep-module vocabulary — module, interface, depth, seam, adapter, leverage, locality — plus a deepening guide and a parallel-subagent design pattern, none of which is repo configuration.

## Considered options

- **Move `triage-labels.md` into `triage` and keep the mapping as a file.** The label vocabulary would still live somewhere editable. Rejected because the file's content was its own default — a table mapping each name to itself. A file that says nothing until someone edits it is worse than a sentence telling the agent to read the labels that exist.
- **Point `tdd` and `improve-codebase-architecture` at the official design guidelines for whatever language or framework is in use**, and drop `codebase-design`. Rejected on what those guidelines contain: framework documentation gives idioms and conventions, not a vocabulary for judging whether an interface is too shallow or where a seam belongs. `improve-codebase-architecture` binds its whole vocabulary to `codebase-design` — the glossary, the principles, and the design-it-twice pattern — and its report format instructs "if a term isn't in the glossary, reach for one that is before inventing a new one" — substituting per-framework docs removes the thing keeping that output consistent, and buys one picker entry.
- **Fold the glossary into `improve-codebase-architecture` and drop the standalone skill.** Same picker saving with no rewrite, since that skill is the vocabulary's main consumer. Rejected by the curator in favour of leaving it reachable on its own: `tdd` also cites it, and a vocabulary you can only reach by starting an architecture review is a vocabulary people stop using.

## Consequences

`plan` is down to five skills — `to-spec`, `to-tickets`, `wayfinder`, `triage`, `domain-modeling` — and every one of them is a thing you do rather than a thing you configure first. Nothing in the marketplace now requires a setup step before first use except credentials, which [0005](0005-credentials-live-in-one-passion-env.md) already handles in one file.

The deletion retired another cross-boundary caveat: `setup-repo` held one of the three `OPTIONAL_REFS` entries in [0017](0017-skill-pointers-carry-their-namespace.md). Two remain — `grill-with-docs` → `domain-modeling` for Service and Support, and `wayfinder` → `prototype` for Ops.

Anyone whose repository genuinely uses a different Jira label vocabulary now gets asked at triage time rather than configured in advance. That is more interruption per repo and less setup, which is the right trade at this size and would stop being right if the label sets multiplied.

`setup-repo` was the renamed `setup-matt-pocock-skills` that [0014](0014-the-roster-and-the-names.md) went to some trouble to keep and repoint. It is worth noting that the rename made the removal thinkable: under its old name it read as infrastructure, and under `setup-repo` it read as a step, which invited the question of whether the step was necessary.
