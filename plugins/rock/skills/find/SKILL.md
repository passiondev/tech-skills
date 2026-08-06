---
name: find
description: Find something in Rock RMS from a rough description rather than a name or ID — workflows, pages, people, groups, schedules, registrations, connection requests. Use before inspecting or changing anything, to turn "the volunteer signup thing" into an ID.
---

# Find things in Rock

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" query search "volunteer"
```

`search` spans entity types and is the right first move when you have a phrase.
When you know the type, list it directly:

| Looking for | Command |
| --- | --- |
| Workflow types | `query workflows [--category Volunteers] [--limit 100]` |
| Pages | `query pages [--site 3] [--limit 100]` |
| A person | `query person "jane@example.org"` — name, email, or ID |
| A group | `query group "Nursery Volunteers"` |
| Schedules | `query schedules [--active] [--query "sunday"]` |
| Registration instances | `query registrations [--active] [--query "camp"]` |
| Connection requests | `query connections [--state active] [--opportunity "serve"]` |

No matches usually means the name in Rock differs from the name people say, so
retry with a distinctive word from the middle of the phrase before concluding
it does not exist.

## Reporting back

You are done when every match is reported with its name and its ID —
`/rock:inspect` and everything downstream take the ID:

```
Volunteer Signup (workflow type 234, category Volunteers, active)
```

Several matches is the normal case, not an error: Rock accumulates
near-duplicate names over years. List them with what tells them apart —
category, active state, route — and ask which one.

## Next

- Full configuration of one of them → `/rock:inspect`
- Numbers, rosters, attendance → `/rock:data`
- What is wrong with a workflow → the `audit` skill, if the `rock-build` plugin
  is installed
