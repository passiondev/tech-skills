---
name: to-spec
description: Turn the current conversation into a spec and publish it to Jira — synthesis of what you have already discussed, not an interview. Spec first, then `/plan:to-tickets`.
disable-model-invocation: true
---

Synthesize a spec — you may know the document as a PRD — from the conversation already in context and your own reading of the codebase, rather than interviewing the user.

The issue tracker is Jira. Fetch a ticket as context with `/jira:ticket`. Triage roles are the five canonical names `/plan:triage` defines; if this project's Jira uses different label strings, ask rather than guessing at the mapping.

## Process

1. Explore the repo until you can name every module the feature touches, every ADR that constrains it, and the domain glossary terms it belongs to. Write the spec in that vocabulary and within those decisions.

2. Sketch the seams at which you will test the feature. Prefer existing seams, take the highest one available, and aim for a single seam across the codebase. Present them to the user and continue once they confirm.

3. Write the spec using the template below. A spec is general prose, so run `/general:to-ste` over it in **flavored** mode before it goes anywhere, exempting the prototype snippets, the identifiers, and the `As an <actor>` user-story frame. Then publish it to Jira and apply the `ready-for-agent` triage label — the spec is triaged by construction. Done when the spec is in Jira under that label; breaking it into tickets is `/plan:to-tickets`, a separate run.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A numbered list, each in the format:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

Cover every actor, every state, and every error path the feature touches.

## Implementation Decisions

This can include:

- The modules that will be built or modified, and the interfaces of those modules
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Name modules and interfaces rather than file paths or code snippets — paths go stale fast.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision, note briefly that it came from a prototype, and trim it to the decision-rich parts.

## Testing Decisions

- The seams you agreed with the user, and the external behaviour each one exercises
- Prior art — similar tests already in the codebase

## Out of Scope

What this spec deliberately does not cover, and why.

## Further Notes

Open questions, and anything that did not fit above.

</spec-template>
