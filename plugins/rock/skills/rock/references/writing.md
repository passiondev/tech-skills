# Changing Rock

Read this before writing anything. The four rules in `SKILL.md` are not repeated
here; they still apply to every operation below.

Writes go one of two ways. A plan file, which is most of them:

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
cat > /tmp/rock-plan.json <<'PLAN'
{ "operation": "update_action", "modification": { ... } }
PLAN
"$R" build /tmp/rock-plan.json
```

One operation per plan file, under `/tmp` — the build script rejects any other
path, so a plan cannot land in a repository. Or a `query` subcommand, for the
four small writes at the end of this file.

## Audit first

Run the audit before repairing anything, including when someone has already
described the fault — the described fault is usually a symptom of a different
one.

```bash
"$R" query audit "Volunteer Signup"
```

`--skip-settings` drops the per-action settings checks: far fewer API calls, at
the cost of the most common real fault. Use it for a first pass over a large
workflow, then run the full audit on the activity that looks wrong.

What it checks:

- Activities with no actions
- The first activity not activated with the workflow
- Duplicate activity or action order values
- Action types pointing at entity types that no longer exist — deleted plugins
- `SendEmail` / `SendSms` actions missing a recipient, subject, or body
- Actions that complete their activity mid-chain, orphaning everything after
- Activities nothing ever activates

Then drill in. The audit names the activity; these say why:

```bash
"$R" query actions <activity_id>            # every action's settings
"$R" query attributes "Volunteer Signup"    # attribute keys and field types
"$R" query workflow "Volunteer Signup" --json
```

Attribute keys are the usual culprit. An email action referencing
`{{ Workflow | Attribute:'Email' }}` where the key is actually `EmailAddress`
renders empty, sends to nobody, and reports success.

Label every finding BROKEN or SMELL — failing, versus untidy:

```
"Volunteer Signup" (workflow type 234) — 2 faults, 1 smell

  BROKEN  Activity "Process Signup" (891), action "Send Confirmation" (1234)
          To is empty. Nobody has received a confirmation from this workflow.

  BROKEN  Activity "Notify Staff" (892) is activated by nothing.
          Its two actions have never run.

  SMELL   Activities 891 and 893 both have order 2.
          Execution order between them is undefined.
```

Done when every finding carries the activity and action IDs a repair plan needs,
and says what did or did not happen to the people the workflow touches — that is
what decides whether it gets fixed today or next quarter. A clean audit is a real
result: say so plainly and list what you checked.

## Show the plan, then stop

A structural diff, with the exact before and after:

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

Deleting an activity deletes every action inside it, so spell that out with the
count. There is no rollback — a partly applied plan stays partly applied, which
is what the yes is for.

## Repair

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
setting, so a wrong key costs you the whole apply and not a line of it.

`reorder_actions` takes every action in the activity, not just the moved ones — a
partial list reorders to a state nobody asked for.

## Create

Get all four of these before touching anything, asking the requester for any you
do not have:

- **Purpose.** What happens, and who it happens to.
- **Data collected.** Each field and its type. Text, Email, Phone, Single Select.
- **Actions taken.** Emails, SMS, assignments, delays, attribute setting.
- **Branching.** Any conditional path, and what decides it.

Then load the catalog. Every action component, block type, field type and
category in the plan resolves through it rather than a remembered ID:

```bash
"$R" catalog show
```

If the request needs an action type the catalog does not have, say so and stop —
it usually means a Rock plugin is not installed, or the component is named
something else.

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
templates silently.

| Operation | Creates |
| --- | --- |
| `create_workflow` | a workflow type, its attributes, activities and actions |
| `create_page` | a page and its blocks |
| `create_checkin_area` | a check-in area, with its locations and schedule |
| `add_action` | an action on an existing activity |
| `add_block` | a block on an existing page |

A check-in area is a group, but it goes here rather than under **Groups** below:
it builds a check-in structure, not a roster.

## Groups

Group membership is not a quiet field. It decides who receives the group's
communications, who appears on its schedule, and — for a security role — who can
see and do things in Rock.

Look the group up first, then the person:

```bash
"$R" query group "Guest Services"        # the group, its type, its roster
"$R" query person "someone@example.com"  # the person ID to add
```

Role names belong to the **group type**, not the group: "Leader" in a serving
team and "Leader" in a small group are different roles with different IDs. Giving
`role` a name resolves it inside that group's own type, which is why the group ID
has to be right before the role name matters. Pass `group_role_id` when the ID is
already in hand.

```
Roster change: "Guest Services" (group 312, type Serving Team)

  [add]    someone@example.com as Leader, active
             gains: group email, Sunday schedule, group leader toolbox
  [status] someone-else@example.com Leader -> inactive
             keeps the membership row and its history

Apply? [y/n]
```

| Operation | Key | Fields |
| --- | --- | --- |
| `create_group` | `group` | `name`, `group_type` or `group_type_id`, and optionally `parent_group_id`, `campus_id`, `description`, `is_active`, `is_public`, `is_security_role`, `schedule_id`, `group_capacity`, `settings` |
| `update_group` | `modification` | `group_id` + `updates` (any of the same field names except `group_type` — a group cannot change type) and optionally `settings` |
| `add_group_member` | `modification` | `group_id`, `person_id`, `role` or `group_role_id`, and optionally `status`, `note`, `is_notified`, `order` |
| `update_group_member` | `modification` | `group_member_id` + `updates` (`role` or `group_role_id`, `status`, `note`, `is_archived`, `guest_count`, `order`) |
| `remove_group_member` | `modification` | `group_member_id` — **deletes the row** |
| `create_group_sync` | `modification` | `group_id`, `role` or `group_type_role_id`, `data_view` or `sync_data_view_id`, and optionally `add_user_accounts`, `schedule_interval_minutes`, `welcome_email_id`, `exit_email_id` |

A `role` given as a name resolves inside the group's own type, which for
`update_group_member` means reading the membership's group back first.

`status` is `active`, `inactive`, or `pending`, and it defaults to `active` here.
Rock's own default is inactive, so a membership created any other way with the
status left out is a member who receives nothing.

`settings` are the group type's attributes, keyed exactly as
`"$R" query group <id>` reports them.

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

`create_group_sync` hands the roster for one role to a data view. On its
schedule, Rock adds everyone the data view returns and **removes everyone it does
not** — including members added by hand, and including the person who set it up.

So check the current roster for that role first. If anyone in it would not come
back from the data view, say so and stop:

```
Sync plan: "Guest Services" (312), role Member <- data view "Active Adults" (71)

  Roster now: 14 Members
  Not returned by the data view: 3
             group sync will remove these three on its first run

Apply? [y/n]
```

Move those people to a role the sync does not own, or widen the data view, before
applying. A sync is also the wrong tool for a roster people maintain by hand; say
that rather than building one.

### Security roles

`is_security_role: true` makes the group grant permissions in Rock. Set it only
when the request is explicitly about access, and name it in the plan when you do.

## Small writes

Four writes are `query` subcommands rather than plan files. They still need the
plan and the yes:

```bash
"$R" query block 4821                            # see current values first
"$R" query block-set 4821 EnableDebug false

"$R" query person-create --first Jane --last Doe --email jane@example.org \
     [--connection-status <id>] [--record-status <id>] [--campus <id>]
"$R" query person-update 8842 Email=jane@example.org NickName=Janie
"$R" query exception-clear [--before YYYY-MM-DD] [--type "NullReference"] [--limit 500]
```

`person-create` makes a real person record, and a duplicate person is harder to
undo than almost anything else here — search for them first. `exception-clear`
deletes rows permanently; say how many it will delete and which type, and prefer
`--type` and `--before` over clearing the log wholesale.

## When no operation fits

Rock has hundreds of entities and these operations name a couple of dozen, so a
request eventually lands outside them — a group requirement, a page context, a
scheduled job. Guessing at an operation that does not exist is one wrong answer
and giving up is the other. `api_request` sends exactly one request, which you
write:

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
  field you omitted becomes null, the created-by audit is gone, and the row gets a
  new Guid. `api_request` refuses a `PUT` without `"full_replace": true`, and that
  acknowledgement is only honest when the body is the entity you just read back
  whole — `Id`, `Guid`, `CreatedDateTime` and all. If you are reaching for it to
  change two fields, reach for `PATCH` instead.
- **A `PUT` writes the old row to disk first**, under the runtime's `snapshots/`
  directory, and does not go at all if that read fails. Report the path it
  prints — it is the only way back.
- **`PATCH` and `PUT` both need a non-empty body.** An empty `PATCH` changes
  nothing and would report success; an empty `PUT` nulls every column.
- **Show the request in the plan** — method, URL, body — before sending it. Every
  other operation has a shape a reader can check against a table. This one has
  none, so the requester is the only check there is.

## Verify, and report partial failure honestly

Re-query, or re-run the audit, and quote what came back rather than restating the
plan:

```bash
"$R" query audit "Volunteer Signup"
"$R" query group 312
```

The build script reports per entity and does not roll back:

```
  ✓ Action "Send Confirmation" (1234) updated
  ✗ Action "Broken Step" (1235) — 400: Invalid EntityTypeId

1 of 2 applied.
```

A partial create leaves a half-built workflow in Rock under a real name. Name it
and say what it is missing, so someone finishes or deletes it rather than finding
it later and assuming it works. Then stop and hand it back — an inconsistent
workflow someone knows about beats a "clean" one rebuilt from guesses.

`Warning:` lines are a separate thing — an unresolved category, a form field
naming an attribute that does not exist — and the entity really is created
despite them, so read them and say what is missing.

Newly created workflows commonly audit dirty on the first pass: an activity
nothing activates, an email with no body yet. Better to find that now.

Done when the report accounts for every line of the plan, applied or not, every
`Warning:` line, and quotes the re-query.
