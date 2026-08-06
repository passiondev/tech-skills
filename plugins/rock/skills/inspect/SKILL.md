---
name: inspect
description: Show the full configuration of one named thing in Rock RMS — a workflow's activities, actions and attributes, a page and its blocks, a block's attribute values, a group's members, a schedule, a registration instance. Use when asked what one of these does, or why its configuration reads the way it does.
---

# Inspect one thing in Rock

Read-only.

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" query workflow "Volunteer Signup"
```

| To see | Command |
| --- | --- |
| A workflow's structure tree | `query workflow "<name or id>"` |
| A workflow's attributes and field types | `query attributes "<name or id>"` |
| One activity's actions, with settings | `query actions <activity_id>` |
| A page and its blocks | `query page "/volunteers"` — name, route, or ID |
| One block's attribute values | `query block <block_id>` |
| A group and its members | `query group "<name or id>" [--limit 50]` |
| A schedule | `query schedule "<name or id>"` |
| A registration instance | `query registration "<name or id>"` |

Most of these take `--json`. Use it when you need exact field names or IDs to
hand to another step; use the default rendering when a person is going to read
the answer. Without a name or ID to start from, get one with `/rock:find`.

## How to read a workflow

`query workflow` prints activities in order, each with its actions. Three
things stop a workflow doing anything at all. Check all three before anything
subtler:

- **Is the workflow type active?** An inactive one never fires.
- **Is the first activity activated with the workflow?** If nothing is, the
  workflow starts and immediately does nothing.
- **Does an action complete the activity mid-chain?** Actions after it never
  run, whatever their configuration says.

Action settings are only fetched by `query actions`, one activity at a time,
because each one is an API call. Start with the tree, then drill into the
activity that matters.

## Reporting back

"What does this workflow do" wants three sentences of prose. Reach for the full
tree when someone is about to change it, or is working out why it broke.

Report the configuration as it stands, and flag what looks wrong. A name is not
evidence: `SendEmail` named "Notify Staff" may send to a person attribute that
has been empty for two years.

## Next

- Why is it broken → the `audit` skill, if the `rock-build` plugin is installed
- Writing a Lava template for one of these → `/rock:lava`
- Seeing a page as rendered rather than configured → `browser screenshot` in
  `/rock:status` (needs the opt-in Playwright install)
