---
name: code-review
description: Two-axis code review — Standards and Spec — of the diff between HEAD and a fixed point. Use when the user asks to review a branch, a PR, or the changes since a commit, tag, or merge-base.
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec?

## Process

### 1. Pin the fixed point

The fixed point is the revision the user named — a commit SHA, branch, tag, `main`, `HEAD~5`. Ask for it if they named none.

Capture two commands and reuse them verbatim from here on:

- `git diff <fixed-point>...HEAD` — three-dot, so the comparison is against the merge-base.
- `git log <fixed-point>..HEAD --oneline` — the commit list.

Done when `git rev-parse <fixed-point>` resolves and the diff is non-empty. If either fails, stop here and report it.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages — Jira keys such as `ABC-123`, or `#45` where the repo also uses GitHub issues. Fetch a Jira ticket with `/jira:ticket`.
2. A path the user passed as an argument.
3. A PRD/spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is.

Done when you hold the spec's path or contents, or the user has confirmed there is none.

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** A documented standard can be a hard violation; a baseline smell is a labelled possibility ("possible Feature Envy"). Skip anything tooling already enforces.

Match each smell against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 4. Spawn both sub-agents in parallel

Send a single message with two `Agent` tool calls, both on the `general-purpose` subagent, so each axis works in a context the other never touches.

**Standards sub-agent prompt** — include:

- The full diff command and commit list.
- The standards-source files found in step 3, **plus the smell baseline and its two rules pasted in full** — the sub-agent has no other access to them.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Apply the two rules above. Under 400 words."

**Spec sub-agent prompt** — include:

- The diff command and commit list.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If step 2 found no spec, send the Standards call alone and say so in the report.

### 5. Aggregate and deliver

Present each sub-agent's report verbatim, lightly cleaned, under `## Standards` and `## Spec`. Each axis keeps its own findings in its own section, so neither can mask the other.

End with a one-line summary: the finding count for each axis, and the worst issue within each — two worst issues, one per axis.

The report is done when it has been through `/general:to-ste` in **flavored** mode; it is prose a human reads, not a procedure. Exempt the quoted hunks, file paths, identifiers, cited standard text, and quoted spec lines — STE rewrites your commentary, never the evidence.
