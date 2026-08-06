# Passion Tech Skills

The Passion City Church technology team's Claude Code plugin marketplace. Install
your department once; it stays current on its own.

## Install

Paste this into Claude Code, with your department in place of the example:

> Set me up with the Passion tech skills. I'm in **local engineering**.
> The instructions are at
> https://github.com/passiondev/tech-skills/blob/main/ONBOARDING.md

Claude reads the document, merges two keys into your `~/.claude/settings.json`,
helps you get a Jira API token, and writes your credentials to
`~/.claude/passion.env`. It shows you every change before making it.

Departments: `global-engineering`, `local-engineering`, `ops`, `analytics`,
`service-and-support`.

If you would rather do it by hand, [`ONBOARDING.md`](ONBOARDING.md) is what
Claude will be reading — the settings block is in there.

## What you get

| Department | Skills | Capability plugins |
| --- | ---: | --- |
| `global-engineering` | 23 | general, jira, dev, plan |
| `local-engineering` | 31 | general, jira, dev, plan, rock, rock-build |
| `ops` | 15 | general, jira, plan |
| `analytics` | 28 | general, jira, dev, plan, rock |
| `service-and-support` | 15 | general, jira, rock |

Skills are invoked as `/plugin:skill` — `/dev:tdd`, `/rock:find`,
`/jira:ticket` — or Claude reaches for them on its own when they fit.

**general** — thinking, writing, learning: `onboard`, `teach`, `research`,
`grilling`, `grill-me`, `grill-with-docs`, `humanize`, `to-ste`
**jira** — `ticket`, `sprint`
**dev** — `tdd`, `code-review`, `diagnosing-bugs`, `implement`, `prototype`,
`codebase-design`, `improve-codebase-architecture`, `resolving-merge-conflicts`
**plan** — `to-spec`, `to-tickets`, `wayfinder`, `triage`, `domain-modeling`
**rock** — read Rock RMS: `find`, `inspect`, `data`, `lava`, `status`
**rock-build** — change Rock RMS: `audit`, `fix`, `create`

Departments are bundles: they hold no skills, only the list of capability
plugins they need. You install one thing.

## Updating

You don't. `autoUpdate` is set on the marketplace, so every Claude Code start
pulls the marketplace and its installed plugins. There are no version numbers —
`main` is what everyone is running, which is why nothing merges without review.

The corollary: a skill can change under you, and one can disappear. If
something behaved differently today, the git history is the changelog.

## This repository is public

Permanently, including its history. Nothing internal goes in — no hostnames, no
credentials, no ticket contents, no notes on how our systems are configured.
Skills that need those read them from `~/.claude/passion.env` at runtime, which
lives in your home directory and never in a repo.

That constraint is load-bearing rather than aspirational. If you are adding
something, assume it will be read by people outside the church, forever.

## Contributing

Open a pull request. One curator reviews and merges; CI checks the manifests,
the dependency graph, and scans for anything that looks like a hostname or a
credential.

Set your commit email before your first commit, in your clone of this repo:

```
git config user.email "<your-id>+<your-handle>@users.noreply.github.com"
```

Commit authorship is published forever like everything else here, and it is the
one field a later edit cannot take back. Your global git identity is untouched —
this is repo-local on purpose.

Most skills here are vendored from [`mattpocock/skills`](https://github.com/mattpocock/skills)
and some have been deliberately changed to fit how we work — Jira instead of
GitHub issues, mostly. [`docs/vendored.json`](docs/vendored.json) records where
every skill came from and whether we have diverged from it. Read it before
"fixing" something that looks odd upstream-shaped.

Twenty-one decisions and their reasoning are in [`docs/adr/`](docs/adr/). Start
with [0001](docs/adr/0001-public-marketplace-repo.md) (why public) and
[0002](docs/adr/0002-capability-plugins-and-department-bundles.md) (why two
layers). [`CONTEXT.md`](CONTEXT.md) defines the vocabulary this repo uses
precisely.

## Licence

MIT. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) — eighteen of the
thirty-one skills are Matt Pocock's work, redistributed under his licence.
