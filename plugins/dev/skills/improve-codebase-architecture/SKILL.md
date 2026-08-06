---
name: improve-codebase-architecture
description: Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick.
disable-model-invocation: true
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

Every suggestion is written in two vocabularies:

- **Architecture** — run the `/dev:codebase-design` skill first and use its glossary exactly: **module**, **interface**, **implementation**, **depth** (deep, shallow), **seam**, **adapter**, **leverage**, **locality**. Its principles bind too: the deletion test, the interface is the test surface, one adapter is a hypothetical seam and two is a real one.
- **Domain** — `CONTEXT.md` names the concepts a seam should be named after. Where it defines "Order," say "the Order intake module," not "the FooBarHandler."

## Process

### 1. Explore

**Hot spots first.** Deepening pays off where change keeps landing, so let recent history pick the ground:

- If the user named a direction — a module, a subsystem, a pain point — take it and skip the history.
- Otherwise read `git log --oneline` back far enough to see which files and areas keep recurring, and start there. Scattered history with no hot spot means widening the net.

Read `CONTEXT.md` and any ADRs in `docs/adr/` covering that ground before you scan.

Then use the Agent tool with `subagent_type=Explore` to walk the codebase and note where you hit friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow**?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

Explore until every candidate you will carry forward has its files named, its friction stated in one sentence, and — wherever you call something shallow — a deletion-test verdict.

### 2. Present candidates as an HTML report

Read [HTML-REPORT.md](HTML-REPORT.md) before drafting: it carries the scaffold, the card fields, the diagram patterns, and the tone rules. The report names the friction and the shape of the fix; the interface itself gets designed in step 3.

**ADR conflicts**: surface a candidate that contradicts an existing ADR only when the friction is real enough to warrant reopening the ADR, and say so in the card — _"contradicts ADR-0007 — but worth reopening because…"_.

Draft the card prose, then run it through the `/general:to-ste` skill in **flavored** mode: the cards are descriptive prose, not a procedure. Exempt the HTML and Mermaid source, file and module names, and the terms STE must not rename — the `/dev:codebase-design` glossary and the strength badges (`Strong`, `Worth exploring`, `Speculative`). The report is unfinished until that pass has run.

Then write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. Open it — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell the user the absolute path.

You are done with step 2 when the file is open, every candidate carries a before/after diagram and a strength badge, the report ends on a top recommendation, and you have asked the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, run the `/general:grilling` skill to walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

As decisions land, run the `/plan:domain-modeling` skill to keep the domain model current:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md`. Create the file lazily if it doesn't exist.
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **User rejects the candidate for a load-bearing reason?** Offer an ADR: _"Want me to record this as an ADR so future architecture reviews don't re-suggest it?"_ Load-bearing means a future explorer would need the reason to avoid re-suggesting the same thing; "not worth it right now" expires and stays unwritten.
- **Want to explore alternative interfaces for the deepened module?** Run the `/dev:codebase-design` skill and use its design-it-twice parallel sub-agent pattern.

The loop ends when the user has an interface they would build — named, with what sits behind the seam and which tests cross it — and every term it introduced or sharpened is in `CONTEXT.md`.
