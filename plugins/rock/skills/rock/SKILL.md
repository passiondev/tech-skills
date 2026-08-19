---
name: rock
description: Anything to do with Rock RMS. Find and inspect workflows, pages, blocks, people, groups, schedules and registrations; pull data views, reports, attendance and background checks; audit a broken workflow and repair it; create workflows, pages and check-in areas; change a group's roster, roles or sync; write and debug Lava; check the connection, refresh the catalog, read exception logs. Use for "fix this workflow", "add her to the serving team", "how many checked in", "what does this page do", "is Rock up".
---

# Rock

One entry point for everything Rock — reading it and changing it:

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" catalog status              # reachable? which Rock version? how old is the catalog?
"$R" query search "volunteer"
```

The first run installs the runtime, which takes about twenty seconds. Nothing
works until `~/.claude/passion.env` holds Rock credentials. Setup, the catalog,
exception logs, screenshots and every connection failure are in
`references/connection.md`.

## Reads are free. Writes are not.

A read costs an API call. A write changes production for everyone who uses Rock,
and there is no undo — no rollback, no staging copy, nothing to restore from. So
every change obeys four rules:

1. **Look it up first.** Never write against an ID from memory or from earlier in
   the conversation. Query it again.
2. **Show the plan, then stop.** Print what will change — the exact before and
   after — and wait for a yes. Not a summary of the plan: the plan.
3. **Say what each change causes.** A role change can hand someone the leader
   toolbox. A status change can drop them off a schedule. A deleted activity
   takes its actions with it.
4. **Change only what was asked for.**

This used to be a second plugin that a department had to install deliberately,
and now it is this paragraph — so it holds exactly as far as it is followed. The
only limit that does not depend on that is the Rock account in `passion.env` and
what it has permission to do.

## Find it

`search` spans entity types and is the right first move from a phrase. When the
type is known, list it directly:

| Looking for | Command |
| --- | --- |
| Anything, from a phrase | `query search "volunteer"` |
| Workflow types | `query workflows [--category Volunteers] [--limit 100]` |
| Pages | `query pages [--site 3] [--limit 100]` |
| A person | `query person "jane@example.org"` — name, email, or ID |
| A group | `query group "Nursery Volunteers"` |
| Schedules | `query schedules [--active] [--query "sunday"]` |
| Registration instances | `query registrations [--active] [--query "camp"]` |
| Connection requests | `query connections [--state active] [--opportunity "serve"]` |

No matches usually means the name in Rock differs from the name people say, so
retry with a distinctive word from the middle of the phrase before concluding it
does not exist. Several matches is the normal case, not an error — Rock
accumulates near-duplicate names over years. List them with what tells them
apart and ask which one.

A name that resolves to nothing, or to several things, exits 1. That is the
lookup reporting its result, not the tool failing — the message on stdout is the
whole story, so read it and retry or ask. An empty collection is different:
`query workflows` on an instance holding none exits 0, because the question was
answered.

Report every match with its name **and its ID**. Everything downstream takes the
ID:

```
Volunteer Signup (workflow type 234, category Volunteers, active)
```

## Read it

| To see | Command |
| --- | --- |
| A workflow's structure tree | `query workflow "<name or id>"` |
| Its attributes and field types | `query attributes "<name or id>"` |
| One activity's actions, with settings | `query actions <activity_id>` |
| A page and its blocks | `query page "/volunteers"` — name, route, or ID |
| One block's attribute values | `query block <block_id>` |
| A group and its members | `query group "<name or id>" [--limit 50]` |
| A schedule | `query schedule "<name or id>"` |
| A registration instance | `query registration "<name or id>"` |
| Data views | `query dataviews [--category <substring>]`, `query dataview "<name or id>"` |
| Reports | `query report "<name or id>"` |
| Attendance occurrences | `query attendance [--group "<name or id>"] [--date YYYY-MM-DD]` |
| One occurrence, with attendees | `query occurrence <id> [--names] [--limit 200]` |
| Background checks | `query bgc [--status <substring>] [--person "<name or id>"]` |
| Check-in configuration | `query checkin [--area "<name or id>"]` |

Most take `--json`. Use it when you need exact field names or IDs for a later
step; use the default rendering when a person is going to read the answer.

Three things stop a workflow doing anything at all. Check all three before
anything subtler:

- **Is the workflow type active?** An inactive one never fires.
- **Is the first activity activated with the workflow?** If nothing is, the
  workflow starts and immediately does nothing.
- **Does an action complete the activity mid-chain?** Actions after it never run,
  whatever their configuration says.

Action settings are fetched one activity at a time, because each is an API call.
Start with the tree, then drill into the activity that matters.

Report the configuration as it stands, and flag what looks wrong. A name is not
evidence: `SendEmail` named "Notify Staff" may send to a person attribute that
has been empty for two years.

## Give the number, and what it covers

Every number ships with its boundaries — the dates it covers, the limit in play,
and what was left out. An attendance query without `--date` returns the most
recent occurrences up to `--limit`, not all of them, and a report that silently
truncated is worse than no answer:

```
Sunday 12 Jan, Kids Ministry: 312 across 4 occurrences.
(Occurrences on that date only; three groups had no occurrence recorded.)
```

## This data is about real people

- **Keep rosters, check results, and person records in the conversation.** Never
  write any of it into a repository — not a scratch file, not a `.md` you are
  drafting, not temporarily. If someone needs a file, put it outside the repo and
  say where.
- **Background check status is need-to-know.** Report the subject of the question
  and nothing around it: whether their check is current, or which are expiring.
- **A screenshot of a Rock page is full of names.** Screenshots stay outside every
  repository.

## Change it

Read `references/writing.md` before writing anything. It holds the audit, the
plan-and-apply loop, and every operation with its fields — the tables are the
difference between a change that lands and a 400 that leaves a workflow
half-built. In outline:

| The request | Where it goes in `references/writing.md` |
| --- | --- |
| "why isn't this workflow running" | **Audit** — run it first, always |
| "fix this action", "reorder these" | **Repair** |
| "build a workflow", "add a block" | **Create** |
| "add her to the serving team", "make him a leader" | **Groups** |
| a person record, a block setting, clearing exceptions | **Small writes** |
| anything with no operation for it | **When no operation fits** |

## Lava

`references/lava.md` covers Rock's template language, and points at the three
reference files beside it. Read it before writing any template — an unknown
filter name renders as silence rather than an error, so filter names come from
the reference and not from memory.

Anything you write that lands in Rock — HtmlContent, Pre/PostHtml, Dynamic Data
SQL, workflow Lava, a form header — follows `references/coding-standards.md`.
Read it before you write, not after.
