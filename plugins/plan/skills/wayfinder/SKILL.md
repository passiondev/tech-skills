---
name: wayfinder
description: Chart a chunk of work too big for one agent session as a shared map of decision tickets in Jira, then resolve them one at a time until the way to the destination is clear.
disable-model-invocation: true
---

A loose idea has arrived — too big for one agent session, and wrapped in fog: the way from here to the **destination** isn't visible yet. This skill charts that way as a **shared map** on the issue tracker, then works its **decision tickets** — questions whose resolution is a decision, not slices of a build to execute — one at a time until the way is clear.

## Plan, don't do

Wayfinder is **planning** by default: each ticket resolves a decision, and what the map produces is decisions, not deliverables. The pull to just do the work is the signal you've reached the edge of the map and it's time to hand off. An effort can override this in its **Notes**, carrying execution into the map itself.

## Refer by name

Every map and ticket is an issue, so it has a **name** — its title. In everything the human reads — narration, the map's Decisions-so-far — refer to it by that name with its link wrapped inside: `[Pick the ingest cadence](url)`, never a bare `ABC-42`.

## The map

The map, its child tickets, and the blocking edges between them live in Jira. Fetch any one of them as context with `/jira:ticket`. The map is a Jira issue labelled `wayfinder:map`; its tickets are child issues of that map; blocking uses Jira's native **Blocks / Is blocked by** link, and the frontier is a JQL query for open children of the map with no open blockers.

The map is an **index**, not a store: a decision lives in exactly one place — its ticket — so the map gists it and links, never restates it.

Read [MAP-FORMAT.md](MAP-FORMAT.md) before writing any issue body, the map's or a ticket's. It holds the map's five sections and what belongs in each, and the one-question shape of a ticket.

Each ticket is sized to one 100K token agent session and carries a `wayfinder:<type>` label — one of `research`, `prototype`, `grilling`, `task` (see [Ticket types](#ticket-types)). Assets created while resolving it are linked from the issue rather than pasted in.

A session **claims** a ticket by assigning it to the dev driving the map, **first**, before any work, so concurrent sessions skip it. That assignee _is_ the claim: an open, unassigned ticket is unclaimed. A ticket is **unblocked** when every ticket blocking it is closed; the **frontier** is the open, unblocked, unclaimed children — the edge of the known.

## Ticket types

Every ticket is either **HITL** — human in the loop, worked *with* a human who speaks for themselves — or **AFK**, driven by the agent alone. A HITL ticket only resolves through that live exchange; the agent never stands in for the human's side of it (a grilling agent that answers its own questions has broken this).

- **Research** (AFK): Reading documentation, third-party APIs, or local resources like knowledge bases to surface a fact a decision waits on. Resolved by a `/general:research` **subagent**. Use when knowledge outside the current working directory is required.
- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to — an outline, a rough take, a stub, or UI/logic code via the `/dev:prototype` skill where `dev` is installed. Links the prototype as an asset. Use when "how should it look" or "how should it behave" is the key question.
- **Grilling** (HITL): Conversation via the `/general:grilling` and `/plan:domain-modeling` skills. The default case.
- **Task** (HITL or AFK): Manual work that must happen before a *decision* can be made — nothing to decide, prototype, or research, but the discussion is blocked until it's done. Signing up for a service so its API can be judged, provisioning access, moving data so its shape can be seen. The one type that *does* rather than decides — it earns its place by unblocking a decision, not by delivering the destination. The agent drives it alone where it can (AFK); otherwise it hands the human a precise checklist (HITL). The answer records what was done and any resulting facts (credentials location, new URLs, row counts) later tickets depend on.

## Fog of war

Chart only what you can already see. Beyond the live tickets lies the **fog of war** — the dim view of decisions and investigations you can tell are coming but can't yet pin down, because they hang on questions still open. Resolving a ticket clears the fog ahead of it, graduating whatever is now specifiable into fresh tickets, until no tickets remain and the way to the destination is clear.

The map's **Not yet specified** section is where that dim view is written down: the suspected question, the area to revisit later. Everything there is in scope, just not sharp enough to ticket.

**Fog or ticket?** The test is whether you can state the question precisely now — _not_ whether you can answer it now.

- **Ticket when** the question is already sharp — even if it's blocked and you can't act on it yet.
- **Not yet specified when** you can't yet phrase it that sharply. A patch of fog is coarser than a ticket: it may graduate into several tickets, or none, once the frontier reaches it.

## Out of scope

Fog only ever gathers _toward_ the destination. The destination fixes the scope, so work beyond it is **out of scope** and belongs in the map's **Out of scope** section: scope, not sharpness, lands it there. It never graduates — the frontier stops at the destination — so it returns only if the destination is redrawn, and then as a fresh effort.

When a ticket that already exists turns out to sit past the destination — mis-scoped in while charting, or exposed by a resolution — **close it** (a closed ticket is unambiguously off the frontier) and leave one line in **Out of scope**: the gist, why it's out, and a link to the closed ticket. Ruling something out of scope is a scoping act, not a step on the route, so it stays out of **Decisions so far**, which records the route actually walked.

## Invocation

Two modes. Either way, resolve **one ticket per session** — research tickets excepted, since subagents resolve those in parallel.

### Chart the map

User invokes with a loose idea.

1. **Name the destination.** Run a `/general:grilling` and `/plan:domain-modeling` session to pin down what this map is finding its way to: a spec to hand off and iterate on, a decision to lock before planning starts, or a change made in place like a data-structure migration.
2. **Map the frontier.** Grill again, **breadth-first** this time: fan out across the whole space rather than deep on any one thread, surfacing the open decisions and the first steps takeable now. **If this surfaces no fog** — the way to the destination is already clear, the whole journey small enough for one session — you don't need a map. Stop and ask the user how they'd like to proceed.
3. **Create the map** (label `wayfinder:map`), in the [MAP-FORMAT.md](MAP-FORMAT.md) shape: Destination and Notes filled in, Decisions-so-far empty, the fog sketched into **Not yet specified**.
4. **Create the tickets you can specify now** as child issues of the map — then wire blocking edges in a **second pass** (issues need ids before they can reference each other). Wiring sorts them into the frontier and the blocked; everything you can't yet specify stays in **Not yet specified**.
5. **Fire the research subagents.** For each `research` ticket you just created, spin up a `/general:research` subagent to resolve it in parallel, capturing its findings on a throwaway `research/<name>` branch with a context pointer from the ticket.
6. Stop — charting is one session's work; it hand-resolves nothing.

### Work through the map

User invokes with a map (URL or issue key). A ticket is **optional** — without one, you pick the next decision, not the user.

1. Load the **map** — the low-res view, not every ticket body.
2. Choose the ticket. If the user named one, use it. Otherwise take the first frontier ticket in order. **Claim it**: assign it to yourself before any work.
3. Resolve it by its type — **zoom as needed**: fetch the full body of any related or closed ticket on demand, and invoke the skills the `## Notes` block names.
4. Record the resolution: post the answer as a **resolution comment**, **close** the issue, and **append a context pointer** to the map's Decisions-so-far.
5. Bring the map back in step with the answer: add newly-surfaced tickets (create-then-wire); graduate any fog now specifiable, clearing each graduated patch from **Not yet specified** so it lives only as its new ticket; rule out of scope anything the answer reveals sits past the destination; update or delete any ticket the decision has invalidated.
