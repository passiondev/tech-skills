# Tech Skills

The Passion City Church technology team's Claude plugin marketplace. It distributes the skills we have tried and approved, so that installing one thing keeps everyone current.

## Language

**Marketplace**:
The single catalogue this repo publishes, declared in `.claude-plugin/marketplace.json`. There is exactly one.
_Avoid_: registry, store, catalog, repo

**Plugin**:
Anything the marketplace lists and a person can install. Always either a capability plugin or a department bundle.
_Avoid_: package, module

**Capability plugin**:
A plugin that contains skills. Its name is the namespace those skills are invoked under, so it is short: `/dev:tdd`.
_Avoid_: skill pack, library

**Department bundle**:
A plugin that contains no skills, only a list of the capability plugins one department needs. Never typed, only installed, so its name may be long.
_Avoid_: group, role, profile, meta-plugin

**Skill**:
One `SKILL.md` plus its supporting files. The unit of behaviour a person actually invokes.
_Avoid_: command, prompt, agent

**Vendored skill**:
A third-party skill copied into this repo rather than referenced from its origin, so that what we ship is what we reviewed.
_Avoid_: mirrored, synced, forked

**Divergence**:
A deliberate change to a vendored skill, recorded in `docs/vendored.json`. The point of recording it is that a plain diff against upstream cannot tell a divergence from an upstream change.
_Avoid_: patch, customisation, drift

**Runtime**:
The executable code a plugin needs, installed outside the plugin so it survives updates. Rock has one, at `~/.claude/passion-rock`. Skills are prose; a runtime is not.
_Avoid_: environment, install, venv

**Passion skill**:
A skill that talks to a Passion system, and so needs credentials to do anything.
_Avoid_: internal skill, private skill

**passion.env**:
The one file every Passion skill reads its credentials from. Lives at a fixed path in the user's home, never in a repo. Filling it in is the entire credential setup.
_Avoid_: dotenv, config, secrets file

**Bootstrap**:
The one-time install of a plugin's own dependencies, into a directory that survives the plugin being updated. Happens on first use, and again only when the plugin's dependencies change.
_Avoid_: setup, install, provision

**Contamination**:
A skill that landed in a source directory because another tool wrote its own built-ins there, rather than because someone chose it. Never shippable.
_Avoid_: pollution, drift

**Curator**:
The one person who merges. There are no versions and no staging, so review is the only thing standing between a commit and thirty people's tooling.
_Avoid_: maintainer, owner, approver

## Shape

```
.claude-plugin/marketplace.json   the catalogue — every plugin is listed here
plugins/<name>/
  .claude-plugin/plugin.json      name, description, dependencies
  skills/<skill>/SKILL.md         one skill; supporting files sit beside it
  runtime/                        executable code, if the plugin has any
docs/adr/                         twenty-three decisions and why
docs/vendored.json                where every skill came from, and what we changed
tests/                            what the runtime scripts send to Rock, asserted
ONBOARDING.md                     read and acted on by Claude Code, not by a person
```

A department bundle is a `plugin.json` with `dependencies` and nothing else — no `skills/`, no `runtime/`.
