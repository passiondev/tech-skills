---
name: audit
description: Diagnose what is wrong with a Rock RMS workflow — empty activities, unreachable actions, broken action type references, missing email settings, duplicate ordering. Use for "audit this workflow", "why isn't this workflow running", or before repairing anything.
---

# Audit a Rock workflow

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" query audit "Volunteer Signup"
```

`--skip-settings` drops the per-action settings checks — far fewer API calls, at
the cost of the most common real fault. Use it for a first pass over a large
workflow, then run the full audit on the activity that looks wrong.

## What it checks

- Activities with no actions
- The first activity not activated with the workflow
- Duplicate activity or action order values
- Action types pointing at entity types that no longer exist — deleted plugins
- `SendEmail` / `SendSms` actions missing a recipient, subject, or body
- Actions that complete their activity mid-chain, orphaning everything after
- Activities nothing ever activates

## Drilling in

The audit names the activity. These say why:

```bash
"$R" query actions <activity_id>        # every action's settings
"$R" query attributes "Volunteer Signup" # attribute keys and field types
"$R" query workflow "Volunteer Signup" --json
```

Attribute keys are the usual culprit. An email action referencing
`{{ Workflow | Attribute:'Email' }}` where the attribute key is actually
`EmailAddress` renders empty, sends to nobody, and reports success.

## Reporting

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
what decides whether it gets fixed today or next quarter.

A clean audit is a real result: say so plainly and list what you checked.

## Next

Repairs go through `/rock-build:fix`, which prints the diff and waits for a yes
before anything lands in production.
