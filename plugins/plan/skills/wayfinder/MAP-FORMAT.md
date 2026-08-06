# Map Format

The body of the map issue and the body of a ticket. What belongs in each section is decided by the rules in [SKILL.md](SKILL.md); this file is the shape.

## The map body

Open tickets are not listed here — they are open child issues, found by query.

```markdown
## Destination

<what reaching the end of this map looks like. One or two lines; every session orients to it before choosing a ticket.>

## Notes

<domain; skills every session should consult; standing preferences for this effort>

## Decisions so far

<!-- the index — one line per closed ticket: enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [<closed ticket title>](link) — <one-line gist of the answer>

## Not yet specified

<!-- in-scope fog you can't ticket yet; graduates as the frontier advances — see "Fog of war" in SKILL.md -->

## Out of scope

<!-- work ruled beyond the destination; closed, never graduates — see "Out of scope" in SKILL.md -->
```

## A ticket body

```markdown
## Question

<the decision or investigation this ticket resolves>
```

The answer is not part of the body: it is posted as a resolution comment when the ticket is closed.
