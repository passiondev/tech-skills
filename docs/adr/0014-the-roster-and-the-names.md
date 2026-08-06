# The roster, and the names

Twenty-three skills ship. The marketplace is `passion-tech`. `setup-matt-pocock-skills` becomes `setup-repo`.

`git ls-files skills` in `~/dev/ai` returns twenty-five tracked skills, and tracked-ness is the filter [0006](0006-vendored-skills-diverge-on-purpose.md) relies on: the seven contaminated skills are all untracked, so they cannot be copied by accident. Two of the twenty-five come out by hand — `ask-matt`, which the brief excluded, and `contribute`.

`contribute` is dropped on cost and fit together. It is a thirteen-stage pipeline for submitting fixes to public GitHub repositories: it forks the target into `~/dev/`, mines merged pull requests for candidates, and pauses for CLA signing. No department in [0008](0008-department-to-capability-mapping.md) does upstream open-source work. It is also, at 192 tokens per turn, the single most expensive skill in the shippable set — every person in every department would carry the most expensive thing we ship for a workflow none of them have. It is an original rather than an upstream copy, so nothing is lost by leaving it in `~/dev/ai` where it is used.

`passion-tech` as the marketplace id is a decision that has to be made before the first person installs, because it is embedded in every `plugin@marketplace` key in everyone's `settings.json` and renaming it means thirty people editing a file. It reads correctly in the two places it appears: `local-engineering@passion-tech` in settings, and `passion-tech` in the `/plugin` picker. `tech-skills` was the alternative, matching the repository, but the repository name is already visible in the `source` block and the picker benefits more from the organisation's name than from a second copy of the repo's.

`setup-matt-pocock-skills` had to be renamed because it names a person thirty Passion staff have no reason to know, and because [0006](0006-vendored-skills-diverge-on-purpose.md) established that we own our copies. `setup-repo` describes what it actually does — configure the current repository's tracker, triage vocabulary, and documentation layout — and reads `/plan:setup-repo`.

## Considered options

- **Keep `contribute`, rewrite it for internal use.** Its thirteen stages encode something real about vetting a change before proposing it. Rejected as a rewrite disguised as a port: nothing of the pipeline survives contact with a private Jira-tracked monorepo, and [0001](0001-public-marketplace-repo.md) means the worked examples cannot be ours.
- **`passion` as the marketplace id.** Shortest, and every plugin in it is a Passion plugin. Rejected because the organisation runs more than a technology team, and a marketplace named for the whole church that contains only engineering tooling will be wrong the first time anyone else wants one.

## Consequences

Dropping `contribute` and `ask-matt` by hand means the tracked-file filter is necessary but not sufficient. Whatever script copies these skills has to carry an explicit exclusion list, and that list has to be visible enough that the next person adding a skill sees it.

`setup-repo` is referenced by name inside five other skills — `wayfinder`, `to-tickets`, `to-spec`, `triage`, and `code-review` — each of which tells the user to run it when configuration is missing. Renaming the directory without patching those five leaves five skills instructing people to run something that does not exist.

*[0019](0019-setup-repo-is-removed.md) deleted the skill, and the referrers had to be edited a second time. Three still named it by then — `to-spec`, `to-tickets`, and `triage`. The reference itself was the durable thing, not the name it pointed at.*
