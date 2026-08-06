# The upstream relationship, and why vendoring still wins

The repo is MIT-licensed and carries a `NOTICE` crediting `mattpocock/skills`, `Copyright (c) 2026 Matt Pocock`. Twenty-one of the twenty-four skills we ship are verbatim copies of that repository, so MIT is not really a choice — it is the licence those files arrive under, and the copyright and permission notice have to travel with them. Our three originals go under the same licence because [0001](0001-public-marketplace-repo.md) already guarantees nothing proprietary is in here, and a public repository with mixed terms is confusing to no benefit. *[0014](0014-the-roster-and-the-names.md) then dropped `contribute`, one of the three originals, so the shipped ratio is twenty-one of twenty-three. Upstream's licence was confirmed as MIT with that copyright line before `LICENSE` and `NOTICE` were written.*

This ADR exists because [0006](0006-vendored-skills-diverge-on-purpose.md) reached the right conclusion for a wrong reason. It argued that vendoring was cheap because these are "prose, not code under daily churn." That is false. `mattpocock/skills` has 204,920 stars, pull requests numbered in the 760s, versioned releases, and shipped fifteen commits on the day this was written. The drift tax is real and continuous.

The conclusion survives on different grounds. Upstream publishes its entire repository as a **single plugin**, `mattpocock-skills`. Depending on it is mechanically possible — `allowCrossMarketplaceDependenciesOn` takes marketplace names on our manifest, and only the root marketplace's allowlist applies — but it is all-or-nothing. There is no way to drop `ask-matt`, no way to split the set across `dev` and `plan` as [0008](0008-department-to-capability-mapping.md) requires, and every skill would be addressed `/mattpocock-skills:tdd`, a cost thirty people pay every day.

The governance objection is heavier still. [0009](0009-no-plugin-versions.md) removed versions and [0010](0010-curator-merges-ci-guards.md) established that review is consequently the only safety mechanism this project has. Depending on upstream would hand a direct, unreviewed channel to thirty people's tooling to an external maintainer pushing many times a day. The brief asked for "skills I have been trying out and approved of" — approval is the whole point, and it is precisely what the dependency removes.

## Consequences

We are forking a fast-moving repository, and the honest prediction is that a manual refresh ritual will be neglected. The mitigation worth building is a scheduled job that diffs our vendored copies against upstream and opens a pull request when they differ — turning "remember to check" into "review this diff," which the workflow in [0010](0010-curator-merges-ci-guards.md) already handles.

That diff will get noisier over time, because Passion-flavouring a skill is exactly what makes it stop matching upstream. Deliberate changes and upstream changes will be indistinguishable to a plain diff unless each vendored skill records the upstream commit it was taken from.

`~/dev/ai` already does this mirroring — commit `e36ec09` is titled "mirror Matt Pocock skills 1:1 with upstream main." That repository is public and has no `LICENSE` file, so those copies are currently redistributed without the attribution MIT requires. Fixing it there is out of scope here, but this repo must not repeat it.
