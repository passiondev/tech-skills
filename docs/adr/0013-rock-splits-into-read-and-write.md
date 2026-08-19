# Rock splits into a read plugin and a write plugin

> **Superseded by [0023](0023-rock-is-one-plugin-with-one-skill.md).** There is one Rock plugin with one skill. Nine commands turned out to be more than a weekly user could hold, and the safety boundary this ADR drew had already been patched over by [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md), routed around by [0022](0022-rock-writes-use-patch-and-one-operation-is-generic.md), and undercut by the last paragraph of this ADR. The reasoning below is why the split was made and is worth reading before anyone proposes it again.

`rock` reads and cannot change anything: finding workflows, pages, blocks, people and groups; inspecting one thing's full configuration; dataviews, reports and attendance; the Lava and action-type references; connection status and catalog refresh. `rock-build` writes: diagnosing a broken workflow, repairing it, and creating new entities.

```
local-engineering    rock  rock-build
analytics            rock
service-and-support  rock
```

This started as a routing problem and turned into a safety one. Today's skill is a single 8.8 KB file whose description is a keyword list — "rock audit", "rock fix", "rock build", "rock create", "fix this workflow" — which is what a skill doing four unrelated jobs looks like. Splitting it improves routing and stops an 8.8 KB body loading to answer "what does this workflow do."

But [0008](0008-department-to-capability-mapping.md) gives Rock to three departments, and only one of them should be changing Rock. As a single plugin, a service and support person asking Claude to "fix this workflow" would have it modify production. Making write capability a separate install means it is granted deliberately rather than arriving as a side effect of needing to look something up.

The line was already drawn in the code. `rock_query.py` is 66 KB and reads; `rock_build.py` is 29 KB and writes. The plugin boundary follows a separation that exists rather than inventing one.

## Considered options

- **One plugin, skills split by entity** — `workflow`, `page`, `data`, `lava`, `status`. Closest to how people think about Rock and to how the split was originally described. Rejected because the safety boundary would then live inside skill instructions, where it is a suggestion, rather than in what a person has installed, where it is a fact.
- **One plugin, skills split by operation** — `audit`, `fix`, `build`, `query`. Smallest change from what exists. Rejected for the same reason, and because "audit" versus "query" is a distinction people have to be taught rather than guess.

## Consequences

Auditing is a read that belongs with writes. Diagnosing a broken workflow changes nothing, but it is the step before repair and is useless separated from it, so it sits in `rock-build`. Someone with read-only Rock cannot ask what is wrong with a workflow — only what it contains.

Two plugins means two bootstraps unless they share one. Both need the same Python and the same dependencies, and [0003](0003-rock-bundles-its-runtime.md) installs those into `${CLAUDE_PLUGIN_DATA}`, which is per-plugin — so `rock-build` should depend on `rock` and reuse its runtime rather than duplicating a second copy of Playwright-less Python and a second `uv sync`. *Resolved by [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md): the shared runtime lives at `~/.claude/passion-rock`, which neither plugin owns.*

The read-only guarantee is only as strong as the scripts behind it. It holds because `rock_query.py` issues no writes, not because anything enforces it, so a write path added to the query script would silently break the boundary. *This was wrong when written — `rock_query.py` already had four write subcommands, so the boundary this ADR describes did not exist until [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md) enforced it.*

Rock's credentials are one account with one permission set. A read-only plugin does not mean a read-only Rock user, so nothing here prevents someone reaching Rock another way with the same credentials from `passion.env`. *This paragraph is the one that eventually won. [0023](0023-rock-is-one-plugin-with-one-skill.md) puts the boundary where this sentence says it actually lives — the Rock account's permissions — and drops the plugin split.*
