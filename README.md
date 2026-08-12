# Passion Tech Skills

The Passion City Church technology team's Claude Code plugin marketplace. Install
your department once; it stays current on its own.

## Install

Paste this into Claude Code. Put your department in place of the example.

> Set me up with the Passion tech skills for **local engineering**.
> Check whether I already have them. Install them only if I do not.
> The instructions are at
> https://github.com/passiondev/tech-skills/blob/main/ONBOARDING.md

Departments: `global-engineering`, `local-engineering`, `ops`, `analytics`,
`service-and-support`.

Claude reads the document, then works through it with you, one step at a time:

- Explains the permission prompts before the first one appears
- Installs your department bundle and turns auto-update on
- Counts the plugins, because a half-installed bundle is easy to miss
- Helps you create a Jira API token, click by click
- Writes your credentials to `~/.claude/passion.env`
- Switches the new skills on without restarting, then runs one on your own work
- Leaves a one-page reference on your machine and opens it

Claude shows you every change before it writes that change. The paste is safe to
repeat. On a machine that already has the marketplace, Claude checks the count
and skips ahead.

You need no command line experience for any of this. Six approvals, four
answers, and one visit to Atlassian.

To check for yourself:

```
claude plugin list | grep passion-tech
```

To do the install by hand, read [`ONBOARDING.md`](ONBOARDING.md) — step 3 is the
whole of it, and it is two commands.

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

You don't. `autoUpdate` is set on the marketplace, so opening Claude Code
fetches the marketplace and its installed plugins. There are no version numbers.
`main` is what everyone runs, which is why nothing merges without review.

Two gaps in that. Headless runs (`claude -p`) do not auto-update, so a machine
that only ever drives these skills from a script or a scheduled job stays frozen
at whatever it installed. And a session already open when `main` moves does not
pick the change up.

Both close by updating every installed plugin, which takes effect on the next
start:

```
claude plugin list | grep -o '[a-z-]*@passion-tech' | sort -u \
  | xargs -n1 claude plugin update
```

`claude plugin marketplace update passion-tech` is not the command for this. It
refreshes the marketplace clone and leaves every installed plugin where it was,
so it reports success and changes nothing you run.

To see what you are on:

```
claude plugin list
```

The version beside each plugin is the commit that plugin runs. Reading the
marketplace clone with `git log` misleads you here, because the clone sits ahead
of the plugins installed from it.

The corollary of no version numbers: a skill can change under you, and one can
disappear. If something behaved differently today, read the git history on
GitHub. Your local copy is a shallow clone with only the current commit in it,
so it cannot tell you what moved.

## This repository is public

Permanently, including its history. Nothing internal goes in — no hostnames, no
credentials, no ticket contents, no notes on how our systems are configured.
Skills that need those read them from `~/.claude/passion.env` at runtime, which
lives in your home directory and never in a repo.

That constraint is load-bearing rather than aspirational. If you are adding
something, assume it will be read by people outside the church, forever.

## Contributing

Open a pull request — `main` takes changes no other way, including from the
curator. One curator reviews and merges; CI checks the manifests, the dependency
graph, and scans for anything that looks like a hostname or a credential. A
pull request cannot merge until that check is green.

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
