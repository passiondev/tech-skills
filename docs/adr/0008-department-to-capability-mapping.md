# The department mapping

Five capability plugins and five department bundles:

```
global-engineering   general dev plan
local-engineering    general dev plan rock
ops                  general     plan
analytics            general dev      rock       (plan added by 0018)
service-and-support  general          rock
```

*[0013](0013-rock-splits-into-read-and-write.md) later split `rock` in two, adding `rock-build` to `local-engineering` only. That is the one change to this table.*

`general` depends on `jira`, so every department gets Jira without naming it.

The groupings consolidated from the seven originally sketched to five as earlier decisions landed — `writing` and `learn` folded into `general` under [0007](0007-what-general-contains.md), and `design` never had enough skills to justify itself once `imagine` was excluded as contamination.

Two readings drove the assignments. `rock` follows the data rather than the job title, which is why analytics has it: the church's data lives in Rock, so the people who analyse that data need to reach it. And `dev` follows whether a person writes code of any kind, not whether they ship application code — analytics writes queries and transformations, which the code skills serve.

Ops is the instructive case. It takes `plan` but not `dev` and not `rock`, which looked contradictory until the cluster was read properly.

## Why `plan` was not split

The mapping suggested splitting `plan` into a tracker half and a codebase half, on the theory that ops wants `triage` and `to-tickets` but not `to-spec` and `wayfinder`. Reading the skills says otherwise. All six write to files in a repository — the tracker configuration lives at `docs/agents/issue-tracker.md`, tickets are files, `domain-modeling` writes `CONTEXT.md` and ADRs — and `setup-matt-pocock-skills` describes its own job as configuring "this repo for the engineering skills."

So the cluster is not "tracker work versus codebase work." It is planning work *in a repository*, and ops does that in the infrastructure repos. The split would have cut across the grain.

*One detail in that reasoning has since changed: [0015](0015-jira-is-assumed-not-configured.md) removed `docs/agents/issue-tracker.md`, because Jira is assumed rather than configured per repo. The conclusion is unaffected — the other five skills still write to files in a repository.*

## Consequences

`triage` is the weakest fit in the set. Its description covers moving "issues and external PRs" through a state machine of triage roles, which is open-source maintainer work; it also has more repository coupling than anything else in the cluster. It stays for now but is the first candidate if `plan` is ever trimmed.

Nothing in this mapping is expensive to change — a department's contents are a dependency array. Adding a capability plugin to a department propagates on the next auto-update. Removing one does too, which means a skill someone had yesterday can vanish today with no notice to them.
