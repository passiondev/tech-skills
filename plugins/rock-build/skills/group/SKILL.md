---
name: group
description: Change a Rock RMS group or its roster — create a group, edit its properties, add or remove members, change someone's role or status, archive a membership, or set up group sync from a data view. Use for "add her to the serving team", "create a group for the volunteers", "make him a leader", "take them off the roster", "sync this group from a data view".
---

# Change a group or its roster

This changes production, and group membership is not a quiet field. It decides
who receives the group's communications, who appears on its schedule, and — for a
security role — who can see and do things in Rock. Say what a change causes
before you make it.

Four steps, in order, every time.

## 1. Look it up

Never write against a remembered ID.

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" query group "Guest Services"     # the group, its type, its roster
"$R" query person "someone@example.com"  # the person ID to add
```

Done when you hold the group ID, the person ID, and the exact role name as the
group reports it.

Role names belong to the **group type**, not the group: "Leader" in a serving
team and "Leader" in a small group are different roles with different IDs. Giving
`role` a name resolves it inside that group's own type, which is why the group ID
has to be right before the role name matters.

## 2. Show the plan, then stop

```
Roster change: "Guest Services" (group 312, type Serving Team)

  [add]    someone@example.com (person 8842) as Leader, active
             gains: group email, Sunday schedule, group leader toolbox
  [status] someone-else@example.com (person 7115) Leader -> inactive
             keeps the membership row and its history

Apply? [y/n]
```

Name what each change gives or takes away. A role change on a serving team can
hand someone the leader toolbox; a status change can drop them off a schedule.
There is no undo — a partly applied plan stays partly applied.

## 3. Apply

One operation per plan file, under `/tmp` — the build script rejects any other
path, so a plan cannot land in a repo:

```bash
cat > /tmp/rock-plan.json <<'PLAN'
{
  "operation": "add_group_member",
  "modification": {
    "group_id": 312,
    "person_id": 8842,
    "role": "Leader",
    "status": "active"
  }
}
PLAN
"$R" build /tmp/rock-plan.json
```

### Operations

| Operation | Key | Fields |
| --- | --- | --- |
| `create_group` | `group` | `name`, `group_type` or `group_type_id`, and optionally `parent_group_id`, `campus_id`, `description`, `is_active`, `is_public`, `is_security_role`, `schedule_id`, `group_capacity`, `settings` |
| `update_group` | `modification` | `group_id` + `updates` (any of the same field names except `group_type` — a group cannot change type) and optionally `settings` |
| `add_group_member` | `modification` | `group_id`, `person_id`, `role` or `group_role_id`, and optionally `status`, `note`, `is_notified`, `order` |
| `update_group_member` | `modification` | `group_member_id` + `updates` (`role` or `group_role_id`, `status`, `note`, `is_archived`, `guest_count`, `order`) |
| `remove_group_member` | `modification` | `group_member_id` — **deletes the row** |
| `create_group_sync` | `modification` | `group_id`, `role` or `group_type_role_id`, `data_view` or `sync_data_view_id`, and optionally `add_user_accounts`, `schedule_interval_minutes`, `welcome_email_id`, `exit_email_id` |

A `role` given as a name resolves inside the group's own type, which for
`update_group_member` means reading the membership's group back first. Pass
`group_role_id` when the ID is already in hand.

`status` is `active`, `inactive`, or `pending`, and it defaults to `active` here.
Rock's own default is inactive, so a membership created any other way with the
status left out is a member who receives nothing.

`settings` are the group type's attributes, keyed exactly as
`"$R" query group <id>` reports them. Rock rejects a key it does not recognise
and the operation fails — it does not skip the setting and carry on.

Rock validates a membership when it saves: a duplicate member, a group over
capacity, an unmet group requirement all come back as errors rather than silent
successes. Report what came back.

### Removing versus archiving

`remove_group_member` deletes the membership row, and with it the trail that the
person was ever in the group. Where the group type keeps history, archive instead:

```json
{"operation": "update_group_member",
 "modification": {"group_member_id": 4471, "updates": {"is_archived": true}}}
```

The row stays, attendance and history stay attached to it, and the person is off
the active roster. Prefer this whenever someone is leaving rather than being
corrected onto a different row.

### Group sync takes the roster over

`create_group_sync` hands the roster for one role to a data view. On its schedule,
Rock adds everyone the data view returns and **removes everyone it does not** —
including members added by hand, and including the person who set it up.

So before creating a sync, check the current roster for that role. If anyone in
it would not come back from the data view, say so and stop:

```
Sync plan: "Guest Services" (312), role Member <- data view "Active Adults" (71)

  Roster now: 14 Members
  Not returned by the data view: 3 (persons 7115, 7240, 7311)
             group sync will remove these three on its first run

Apply? [y/n]
```

Move those people to a role the sync does not own, or widen the data view, before
applying. A sync is also the wrong tool for a roster people maintain by hand;
say that rather than building one.

### Security roles

`is_security_role: true` makes the group grant permissions in Rock. Set it only
when the request is explicitly about access, and name it in the plan when you do.

## 4. Verify

Re-query and report what Rock now holds:

```bash
"$R" query group 312
```

```
Applied 2 of 2. "Guest Services" (312): 15 members, 3 Leaders.
Person 8842 is Leader, active. Person 7115 is Leader, inactive.
```

Done when the report accounts for every line of the plan, applied or not, and
quotes the re-query rather than restating the plan.

## When no operation fits

Groups have corners these six do not reach — requirements, group locations,
scheduling. `/rock-build:fix` documents `api_request`, which sends a single
request you write yourself. Read that section before using it; it is a last
resort with its own rules.
