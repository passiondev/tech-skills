---
name: to-tickets
description: Break an approved spec, plan, or the current conversation into tracer-bullet tickets that declare their blocking edges, and publish them to Jira. The step after `/plan:to-spec`.
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets** — tracer-bullet vertical slices, each declaring the tickets that **block** it.

The issue tracker is Jira. Fetch a ticket as context with `/jira:ticket`. Triage roles are the five canonical names `/plan:triage` defines; if this project's Jira uses different label strings, ask rather than guessing at the mapping.

## Process

### 1. Gather context

If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase

Explore the codebase if you have not already. Ticket titles and descriptions use the project's domain glossary vocabulary and respect the ADRs in the area you are touching.

Look for **prefactoring** that makes the implementation easier: make the change easy, then make the easy change.

### 3. Draft tracer-bullet slices

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Each slice fits in a single fresh context window
- Prefactoring lands first, and blocks the slices that need it

</vertical-slice-rules>

Give each ticket its **blocking edges** — the other tickets that must complete before it can start.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change — rename a column, retype a shared symbol — whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket — green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list: title, **blocked by**, and the end-to-end behaviour the ticket delivers.

Ask the user:

- Does the granularity feel right — should any ticket be merged or split?
- Are the blocking edges correct — does each ticket depend only on the tickets that genuinely gate it?

Iterate until the user approves the breakdown.

### 5. Publish the tickets to Jira

Ask which Jira project to publish into if it is not obvious from the conversation, and confirm the project and the ticket count before creating anything.

Publish one issue per ticket, in dependency order (blockers first) so each ticket's blocking edges can reference real keys. Use Jira's native **Blocks / Is blocked by** issue link for the edges. Apply the `ready-for-agent` triage label unless instructed otherwise — the tickets are agent-grabbable by construction. Leave any parent issue as you found it: reference it from the new tickets rather than closing or editing it.

If the user asks to keep the tickets local instead, write one file per ticket under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order. Use the same template, with `# <NN> — <title>` as the heading, the ticket numbers as the blocking edges, and a `**Status:** ready-for-agent` line in place of the label.

<ticket-template>

## Parent

A reference to the parent issue on the tracker. Omit this section when the source was not an existing issue.

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, rather than a layer-by-layer implementation list.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- A reference to each blocking ticket, or "None — can start immediately".

</ticket-template>

Keep every ticket at the level of behaviour: file paths and code snippets go stale fast. Exception: where a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it trimmed to the decision-rich parts, and note that it came from a prototype.

Every ticket body goes through `/general:to-ste` in **flavored** mode before it reaches Jira or disk — a ticket description is prose, not a procedure. Code blocks, identifiers, and acceptance-criteria phrasing that matches the tracker's conventions pass through unchanged.
