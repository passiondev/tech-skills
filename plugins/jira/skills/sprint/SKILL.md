---
name: sprint
description: >
  Your queue in the current Jira sprint — every issue assigned to you in one
  project's open sprint, with what is overdue, in progress, and still to do.
  Use when the user asks about their own sprint work (what they are working on,
  what is overdue, what to pick up next), or wants a standup summary or sprint
  report. Scoped by project key; for one issue named by its issue key, use
  `/jira:ticket`.
---

# Your sprint queue

## Step 1: Run the report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/sprint/scripts/sprint_report.py"
```

- `--project <KEY>` — add it whenever the user names a project; without it the script uses `JIRA_PROJECT`.
- `--json` — the raw data, for answering a specific question. Omit it for the rendered markdown report.
- `--out <path>` — write that markdown to a file instead of stdout.

Credentials come from the environment, falling back to `~/.claude/passion.env` — the script works from any directory.

## Step 2: Lead with what needs attention

Overdue first, then in progress, then the rest of the queue — in the full report and in a one-line answer alike.

A specific question — "what's overdue?", "what should I pick up next?" — is answered from the JSON in a sentence or two, naming the issue keys. A request for a report, a standup summary, or an overview gets the markdown as it stands.

## Cookbook

<If: the sprint has no issues assigned to them>
<Then: the project key is probably wrong, or no sprint is open. Say which is likelier, and offer to try another project.>

<If: the user asks about someone else's work>
<Then: the report only ever covers the authenticated user. Say so, and offer to write the JQL for the other person instead.>
