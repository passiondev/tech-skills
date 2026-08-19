---
name: create
description: Build something new in Rock RMS — a workflow with its activities and actions, a page with blocks, a check-in area — or add an action or block to something that already exists. Use for "create a workflow", "build a page", "add a block", "set up a new signup form".
---

# Create something in Rock

This changes production. Five steps, in order, every time.

Anything you write that lands in Rock — HtmlContent, Pre/PostHtml, Dynamic Data
SQL, workflow Lava, a form header — follows the coding standards in
`/rock:lava`'s `references/coding-standards.md`. Read it before you write, not
after.

## 1. Understand the request

Get all four before touching anything, asking the requester for any you do not
have:

- **Purpose.** What happens, and who it happens to.
- **Data collected.** Each field and its type. Text, Email, Phone, Single Select.
- **Actions taken.** Emails, SMS, assignments, delays, attribute setting.
- **Branching.** Any conditional path, and what decides it.

## 2. Load the catalog

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" catalog show
```

Every action component, block type, field type and category in the plan resolves
through the catalog rather than a remembered ID. If the request needs an action
type the catalog does not have, say so and stop there — it usually means a Rock
plugin is not installed, or the component is named something else.

## 3. Show the plan, then stop

```
Plan: create workflow "Volunteer Signup"

  Category:   Volunteers
  Attributes: FirstName (Text), EmailAddress (Email), Ministry (Single Select)

  ├─ Fill Out Form            (activated with workflow)
  │    └─ UserEntryForm — FirstName, EmailAddress, Ministry
  └─ Process Signup
       ├─ SendEmail  → {{ Workflow | Attribute:'EmailAddress' }}
       └─ SendEmail  → volunteers team

Create? [y/n]
```

Show the attribute **keys** you will create, not the labels — every Lava template
written against this workflow depends on them, and renaming a key later breaks
templates silently. Lava in any action setting comes from `/rock:lava`.

Nothing is created until the requester answers yes.

## 4. Apply

```bash
cat > /tmp/rock-plan.json <<'PLAN'
{ "operation": "create_workflow", ... }
PLAN
"$R" build /tmp/rock-plan.json
```

| Operation | Creates |
| --- | --- |
| `create_workflow` | a workflow type, its attributes, activities and actions |
| `create_page` | a page and its blocks |
| `create_checkin_area` | a check-in area |
| `add_action` | an action on an existing activity |
| `add_block` | a block on an existing page |

A group, its members, or its sync is `/rock-build:group`. A check-in area is a
group too, but `create_checkin_area` stays here: it builds a check-in structure
with its locations and schedule, not a roster.

Plan files live under `/tmp`; the build script rejects any other path, so a plan
cannot land in a repository.

## 5. Report what exists now

The script reports per entity and does not roll back:

```
  ✓ WorkflowType "Volunteer Signup" (234)
  ✓ Activity "Fill Out Form" (891)
  ✗ Action "Send Confirmation" — 400: Invalid EntityTypeId

2 of 3 created.
```

A partial create leaves a half-built workflow in Rock under a real name. Name it
and say what it is missing, so someone finishes or deletes it rather than finding
it later and assuming it works.

A settings key Rock does not recognise fails the operation on the spot, so a
create can stop with the workflow and its activities in place and an action left
unconfigured. That is what the per-entity report is for. `Warning:` lines are a
separate thing — an unresolved category, a form field naming an attribute that
does not exist — and the entity really is created despite them, so read them and
say what is missing.

Then run `/rock-build:audit` and report its output. Newly created workflows
commonly audit dirty on the first pass — an activity nothing activates, an email
with no body yet — and it is better to find that now.

Done when the report accounts for every entity in the plan, created or not, every
`Warning:` line, and the re-audit.
