---
name: fix
description: Repair an existing Rock RMS workflow — change action settings, rename or reorder actions, move an action between activities, delete a broken action or activity, update workflow and activity properties, set a block attribute. Use for "fix this workflow", "update this action", "reorder these", after an audit has found something.
---

# Repair a Rock workflow

This changes production. Four steps, in order, every time.

Where a repair means editing code that lands in Rock — action Lava, a form
header, a Dynamic Data query — it follows the coding standards in `/rock:lava`'s
`references/coding-standards.md`. Bring the part you touched up to standard and
leave the rest.

## 1. Audit first

Run `/rock-build:audit`, including when someone has already described the fault —
the described fault is usually a symptom of a different one. Done when you hold
current activity and action IDs for everything you are about to change.

## 2. Show the plan, then stop

Print a structural diff — the exact before and after — and wait for a yes:

```
Fix plan for "Volunteer Signup" (workflow type 234)

  Activity "Process Signup" (891)
    [update] Action "Send Confirmation" (1234)
               To:  ""  ->  "{{ Workflow | Attribute:'EmailAddress' }}"
    [delete] Action "Broken Step" (1235)
               entity type 4471 no longer exists
    [reorder] 1234, 1236, 1237
               resolves duplicate order 2

Apply? [y/n]
```

Say what each change causes. Deleting an activity deletes every action inside it,
so spell that out with the count. There is no undo and no rollback — a partly
applied plan stays partly applied, which is what the yes is for.

## 3. Apply

One operation per plan file, under `/tmp` — the build script rejects any other
path, so a plan cannot land in a repo:

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
cat > /tmp/rock-plan.json <<'PLAN'
{
  "operation": "update_action",
  "modification": {
    "action_type_id": 1234,
    "settings": {
      "To": "{{ Workflow | Attribute:'EmailAddress' }}",
      "Subject": "Thanks for signing up!",
      "Body": "<p>See you Sunday.</p>"
    }
  }
}
PLAN
"$R" build /tmp/rock-plan.json
```

### Operations

| Operation | `modification` |
| --- | --- |
| `update_action` | `action_type_id` + `settings` (component settings) or `updates` (`name`, `order`, `action_type`, `complete_on_success`, `complete_activity_on_success`) |
| `delete_action` | `action_type_id` |
| `move_action` | `action_type_id`, `target_activity_type_id` |
| `reorder_actions` | `action_order`: the full list of action IDs, in order |
| `update_activity` | `activity_type_id` + `updates` (`name`, `is_activated_with_workflow`, `order`) |
| `delete_activity` | `activity_type_id` — **removes its actions too** |
| `update_workflow` | `workflow_type_id` + `updates` (`name`, `is_active`, `description`) |

The audit supplies the IDs. An `action_type` name resolves through
`"$R" catalog show`, but `settings` keys go to Rock verbatim — take each key
exactly as `"$R" query actions <activity_id>` reports it. Rock rejects a key it
does not recognise, and the operation fails on it rather than skipping that one
setting, so a wrong key costs you the whole apply and not a line of it. Adding an
action or block that is missing entirely is `/rock-build:create`.

`reorder_actions` takes every action in the activity, not just the moved ones — a
partial list reorders to a state nobody asked for.

A block attribute is a different, smaller thing:

```bash
"$R" query block 4821                      # see current values first
"$R" query block-set 4821 EnableDebug false
```

A group, its roster, or its sync is `/rock-build:group` — different entities,
different confirmation, different ways to get it wrong.

### When no operation fits

The table above covers what this skill was built for. Rock has hundreds of
entities and this plugin names a couple of dozen, so a request eventually lands
outside them — a group requirement, a page context, a scheduled job. Guessing at
an operation that does not exist is one wrong answer and giving up is the other.
`api_request` sends exactly one request, which you write:

```bash
cat > /tmp/rock-plan.json <<'PLAN'
{
  "operation": "api_request",
  "request": {
    "method": "PATCH",
    "endpoint": "GroupRequirements/12",
    "body": {"MustMeetRequirementToAddMember": true}
  }
}
PLAN
"$R" build /tmp/rock-plan.json
```

Read the entity before you change it. `GET` is available here for that reason,
and it is how you learn the field names Rock actually uses:

```json
{"operation": "api_request",
 "request": {"method": "GET", "endpoint": "GroupRequirements/12"}}
```

Then:

- **`PATCH` changes some fields.** It sets what you send and leaves everything
  else alone. This is the verb for almost every edit.
- **`PUT` replaces the entity.** Rock copies every column out of your body, so a
  field you omitted becomes null, the created-by audit is gone, and the row gets
  a new Guid. `api_request` refuses a `PUT` without `"full_replace": true`, and
  that acknowledgement is only honest when the body is the entity you just read
  back whole — `Id`, `Guid`, `CreatedDateTime` and all. If you are reaching for
  it to change two fields, reach for `PATCH` instead.
- **A `PUT` writes the old row to disk first**, under the runtime's `snapshots/`
  directory, and does not go at all if that read fails. Report the path it
  prints — it is the only way back.
- **`PATCH` and `PUT` both need a non-empty body.** An empty `PATCH` changes
  nothing and would report success; an empty `PUT` nulls every column.
- **Show the request in the plan** — method, URL, body — before sending it. The
  named operations have shapes a reader can check against the table. This one has
  none, so the requester is the only check there is.

Nothing here skips a step: `api_request` goes through the same `rock.sh`, the same
write guard, and the same yes as everything above.

## 4. Verify

Re-run `/rock-build:audit` and report its output:

```
Applied 3 of 3. Re-audit: 0 faults, 1 smell (unchanged — activities 891/893
still share order 2, deliberately left alone).
```

Done when the report accounts for every line of the plan, applied or not, every
`Warning:` line, and quotes the re-audit.

## Partial failure

The build script reports per entity:

```
  ✓ Action "Send Confirmation" (1234) updated
  ✗ Action "Broken Step" (1235) — 400: Invalid EntityTypeId

1 of 2 applied.
```

Stop there and hand it back — an inconsistent workflow someone knows about beats
a "clean" one rebuilt from guesses.
