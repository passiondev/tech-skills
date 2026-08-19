# Rock is one plugin with one skill

`rock` is the only Rock plugin, and `/rock:rock` is the only Rock command. The nine skills that were spread across `rock` and `rock-build` are now one `SKILL.md` with four reference files beside it. `rock-build` is retired: its operations, its runtime script and its entry point moved into `rock`, and `local-engineering` no longer names it. The read/write boundary is no longer something a person installs.

This supersedes [0013](0013-rock-splits-into-read-and-write.md) and the guard half of [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md).

## Nine commands is more than anyone holds

[0013](0013-rock-splits-into-read-and-write.md) split one 8.8 KB skill into nine, and the split was right about routing: a description that is a keyword list is what a skill doing four unrelated jobs looks like. What it did not account for is that the nine names are a thing a person has to know. The report that prompted this was from someone who uses these tools every week and still could not remember which of `find`, `inspect`, `data`, `status`, `lava`, `audit`, `fix`, `create` and `group` to reach for — and being wrong was not free, because `/rock:find` and `/rock-build:group` were in different plugins with different install states.

The router never needed nine skills. It needs one description that covers Rock, and Rock is one system: the same person, in the same conversation, looks a group up and then changes its roster. Splitting that into two commands in two plugins described the code's structure rather than the work.

## What the split was buying, and whether it held

The safety argument in [0013](0013-rock-splits-into-read-and-write.md) is the part worth taking seriously: [0008](0008-department-to-capability-mapping.md) gives Rock to three departments and only one of them should be changing it, so write capability arriving as a separate install means it is granted deliberately rather than as a side effect of needing to look something up.

Three things had already happened to that argument.

**It never covered the whole script.** [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md) found four write subcommands sitting inside `rock_query.py`, in the read-only plugin, and patched an environment-variable guard over them rather than moving them. The boundary from the day it was drawn was a plugin split plus a guard, not a plugin split.

**The write half was broken anyway, and the fallback had no guard at all.** [0022](0022-rock-writes-use-patch-and-one-operation-is-generic.md) is the record: four of the seven repair operations 400'd on arrival, the attribute-value writes had never worked, groups were absent entirely — and what people did about it was go back to an archived repo and use its client directly. A boundary whose effect is to push work onto tooling with no guard, no plan file and no confirmation is not protecting anything.

**The install is per-department; the credentials are per-person.** [0013](0013-rock-splits-into-read-and-write.md) says so in its last paragraph and then does not follow it: "a read-only plugin does not mean a read-only Rock user." Someone with an admin Rock account and the read-only plugin was one install away from writing, and the install is a request to a colleague. The account is where the real limit lives, and unlike a plugin split it is a limit Rock enforces and an administrator can tighten per person. `references/connection.md` now says to ask for the narrowest account that does the job, which is the first time this repo has said it anywhere a person setting up Rock will read.

## What this costs the two read-only departments

Plainly: Analytics and Service and Support installed `rock` and could not change Rock. They install `rock` now and can, as far as their Rock account allows. Nobody asked for that and it is not an improvement — it is the price of one command, and the mitigation is the account rather than the manifest.

The four rules at the top of `SKILL.md` — look it up, show the plan and stop, say what each change causes, change only what was asked — are what stands in for the split. They are instructions, and instructions hold as far as they are followed. That sentence is in the skill too, because a safety rule that presents itself as a guarantee is worse than one that admits what it is.

## The guard changes meaning and stays

`ROCK_ALLOW_WRITES` used to answer "which plugin are you". It now answers "did you come through `rock.sh`". The runtime is copied to `~/.claude/passion-rock`, outside the plugin and outside the plugin system, so both scripts sit on disk where anything can run them directly — and running `rock_build.py` by hand is precisely what the old fallback did. `rock.sh` sets the variable; nothing else does; every write path refuses without it.

That is a smaller guard than it was, and it is honest about its size: it stops a write that skips the entry point, which is the path that carries no logging and no plan file. It does not stop anyone who sets the variable. The refusal messages now name `rock.sh` instead of a plugin that no longer exists.

## One skill, four references

A naive merge would be a 900-line `SKILL.md` loaded in full to answer "is Rock up". The split is by when a file is needed:

| | |
| --- | --- |
| `SKILL.md` | the entry point, the four rules, every read command, the privacy rules |
| `references/writing.md` | the audit, the plan-and-apply loop, every operation and its fields, `api_request` |
| `references/connection.md` | setup, catalog, exception logs, browser opt-in, where state lives, failure triage |
| `references/lava.md` | template guidance, pointing at the three vendored reference files beside it |

Reads and the four rules are inline because reads are most of the traffic and because a rule one file away from the model is a rule it may not have read before it reaches for a write. Everything else is loaded when the work calls for it: `writing.md` only when something is about to change, `connection.md` only during setup or a failure, `lava.md` only when there is a template.

## Considered options

- **One plugin, keep the nine skills.** The honest runner-up. It fixes the two-plugin problem — one install, no `/rock-build:` prefix, no half-installed department — and keeps nine descriptions for the router to match against, which is real precision this loses. Rejected because the report was about the commands, not the install: nine names is still nine names.
- **One plugin, three skills: read, write, lava.** Rejected because "which of three" is still a question a person has to answer, and the read/write line is exactly the line the person asking "why is this workflow broken, can you fix it" does not draw. That request crosses it mid-sentence.
- **Keep the split and add a tenth skill that routes to the other nine.** Ten commands to reduce nine, and the router already does this job from descriptions.
- **Leave it and teach the nine.** What [0013](0013-rock-splits-into-read-and-write.md) assumed would happen. Rejected on evidence: someone using them weekly for months had not learned them, and the cost of guessing wrong was a command in a plugin they might not have.
- **Keep `rock-build` but move every skill into `rock`.** Splits the difference and gets the worst of it: one command, but the write operations still ship in a plugin a department may not have installed, so the skill would have to explain a dependency it cannot see.

## Consequences

Skill counts drop: `local-engineering` 32 to 24, `analytics` 28 to 24, `service-and-support` 15 to 11. Analytics and Local Engineering are now identical installs, which is a fact about [0008](0008-department-to-capability-mapping.md) worth noticing rather than a problem — the thing that distinguished them was write access to Rock.

Token cost moves in both directions. A read used to load one small skill; it now loads a larger `SKILL.md` and needs nothing else. A write loads that `SKILL.md` and then `writing.md`, so it costs one extra file read. Reads are the common case, so this is roughly neutral in aggregate and worse for the individual write.

Routing precision is a genuine loss. Nine descriptions gave the router nine chances to match a request; one broad description has to catch all of them. If Rock requests start landing nowhere, the fix is that description — not a second skill.

`~/.claude/passion-rock` does not move, so nobody reinstalls anything and no catalog is lost. The bootstrap deletes the stale `.installed-build` stamp `rock-build` left behind, because nothing else ever would.

Anyone who typed `/rock:find` will find it gone. There are no aliases: the plugin system has no redirect, and a pointer that resolves to something subtly different is worse than one that fails. Typing `/rock` shows the one entry.

`docs/vendored.json` now records one Rock skill where it recorded nine. The provenance chain is one step longer and worth stating: `rock-tools` shipped one skill, [0013](0013-rock-splits-into-read-and-write.md) split it into nine, this merges it back — with the operations, the group work and the write-shape fixes that were not there the first time.

Two of `check.py`'s Rock guards move rather than change. `rock-write-shapes` keys its allow-list on the new path of `rock_build.py`; `write-guard` still requires every write in `rock_query.py` to be listed in `WRITE_COMMANDS`, but its failure text no longer says "a read-only install could reach them", because there is no read-only install.
