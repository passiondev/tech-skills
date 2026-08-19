# tech-skills owns the Rock client; rock-tools is archived

The Rock client code moves into this repo and this repo becomes its only home. `rock-tools` is archived with a pointer, and its `jira-pull.sh` comes across too. There is one copy of the code, so there is nothing to sync.

Once [0003](0003-rock-bundles-its-runtime.md) put the runtime inside the plugin, the choice was between one canonical copy and two copies with a promotion step between them. Two copies drift. Every mechanism for preventing that — a sync command, a CI equality check, a release checklist — is machinery that exists only to paper over having made a copy in the first place. *This repository now carries the CI equality check that sentence rejects, for `passion_env.py` alone. Every skill reaches its own runtime through `${CLAUDE_PLUGIN_ROOT}`, which resolves to whichever plugin runs. So no script in `jira` can name a file in `rock` by a path that survives an install. A department that installs one and not the other still needs working credentials, so one copy per plugin is a floor rather than a choice. The check counts per plugin rather than in total, and fails a second copy inside one plugin, which is the copy somebody made. The argument above still holds for that one.* And there was little left to keep separate: `rock-tools` tracks twenty files, of which nineteen are the Rock runtime, the rock skills, and scaffolding.

Developing in public was the objection, and two facts answered it. The scripts contain no Passion hostnames, credentials, or references of any kind — `config.yaml` names environment *variables*, not their values. *`config.yaml` has since been deleted: four of its five keys were read by nothing, and the fifth is now a constant beside the one function that reads it. The claim holds without it — the variable names are in `rock_client.py`.* And everything the tooling produces when pointed at a live Rock instance is already gitignored: `catalog.json`, `.venv/`, `*.log`, `screenshots/`, `data/reports/`, `.env`. The dangerous output was never in version control.

## Considered options

- **rock-tools stays canonical, with `just sync-rock` plus a CI check that the copies match.** Keeps Rock development private and makes publishing an explicit act. Rejected because the private dev loop was protecting nothing that is actually private, and the CI job would exist solely to detect a problem we can decline to create. *A CI equality check does now exist, for `passion_env.py` alone, and the note above says why the plugin boundary forces it.*
- **rock-tools stays canonical, vendored by hand at release.** The human reading the diff is the strongest leak check available, but nothing fails when the step is skipped.

## Consequences

Rock work is public from now on, so [0001](0001-public-marketplace-repo.md)'s rule applies to every commit here — including commit messages, test fixtures, and anything pasted into a skill as an example. A real Rock page ID or person record in an example is a leak.

`setup.md` in the current rock skill has to be rewritten before it lands. It names our Rock hostname and describes cookie authentication as bypassing Rock's Bearer token enforcement. The hostname belongs in the environment. The authentication note describes a supported Rock endpoint and can stay, but not framed as a bypass.

Archiving `rock-tools` will break anyone's muscle memory for `just rock-*`. The recipes were one-line wrappers, so the replacement is the script invocation the skills now use.
