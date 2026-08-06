# Skill pointers carry their plugin namespace, and CI checks they resolve

Every reference one skill makes to another is written `/plugin:skill` — `/dev:tdd`, `/plan:domain-modeling` — and the `cross-references` check in `.github/scripts/check.py` fails the build on any pointer that does not resolve.

Upstream is one flat directory of skills, so `/tdd` is a real command there. Vendoring those skills into a marketplace silently broke that: [0002](0002-capability-plugins-and-department-bundles.md) makes the plugin name the namespace, so the command is `/dev:tdd` and the bare form names nothing. Thirty-four pointers across twelve files arrived that way and nobody noticed, because a dangling pointer in prose fails quietly — the agent reads a sentence about a skill it cannot invoke and improvises.

The department split in [0008](0008-department-to-capability-mapping.md) adds a second failure the namespace alone does not fix. A correctly written `/plan:domain-modeling` cited from a `dev` skill still dangles for Analytics, who install `dev` without `plan`. Four pointers crossed a boundary some department does not have:

| Referrer | Points at | Missing for |
| --- | --- | --- |
| `general:grill-with-docs` | `/plan:domain-modeling` | analytics, service-and-support |
| `dev:improve-codebase-architecture` | `/plan:domain-modeling` | analytics |
| `plan:setup-repo` (`domain.md`) | `/dev:improve-codebase-architecture` | ops |
| `plan:wayfinder` | `/dev:prototype` | ops |

All four are enrichments rather than prerequisites, so each sentence now says so and names the departments that lack it, and each is listed in `OPTIONAL_REFS` with its reason. Anything else unreachable fails CI.

## Considered options

- **Add the missing dependencies** — `general` depends on `plan`, `dev` depends on `plan`. Every pointer resolves everywhere and the check reduces to a spelling rule. Rejected because it collapses the mapping [0008](0008-department-to-capability-mapping.md) exists to express: the answer to "ops only needs general and plan" cannot be that everyone gets everything. Analytics would gain the whole ticket-authoring cluster that [0007](0007-what-general-contains.md) deliberately keeps away from them.
- **Delete the four cross-boundary pointers.** No exception list, no prose caveats. Rejected because the pointers are correct for the departments that do have both plugins, and Global and Local Engineering are most of the pointer-following traffic. Removing a working cross-reference to satisfy a checker is the checker winning an argument it should lose.
- **Leave the bare `/tdd` form and rely on the agent to find the skill by name.** Plausible — the Skill tool takes a name. Rejected because it is only plausible: it depends on undocumented matching behaviour, and it would keep our copies byte-identical to upstream for no benefit we can name, while [0006](0006-vendored-skills-diverge-on-purpose.md) already expects Passion-specific patches.

## Consequences

Ten skills that were byte-identical to upstream now differ, and are marked `diverged` in `docs/vendored.json` for it. That is the intended cost, but it does mean the namespacing patch has to be re-applied by hand every time one of those ten is refreshed from upstream — the weekly drift issue is where that surfaces.

`OPTIONAL_REFS` is a list of four exceptions in a checker, which is a shape that rots if it grows. The check fails on a stale entry as well as a new violation, so the list cannot quietly outlive the prose it excuses. A fifth entry should be read as evidence the department mapping wants revisiting, not as a line to add.

Reference files, not just `SKILL.md`, carry pointers — `HTML-REPORT.md`, `AGENT-BRIEF.md`, `domain.md`. The check walks every `.md` under `plugins/` for that reason.
