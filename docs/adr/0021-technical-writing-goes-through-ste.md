# Technical writing goes through STE

Seven skills in this marketplace produce prose a colleague reads and acts on: a ticket, a spec, a ticket body, an ADR, a code review, an architecture card, a triage note. Each was writing that prose in whatever register the model reached for. They now finish by running the draft through `/general:to-ste`, which converts it to ASD-STE100 Simplified Technical English and lints it to prove the slop score dropped.

The seven are `dev:code-review`, `dev:improve-codebase-architecture`, `jira:ticket`, `plan:domain-modeling`, `plan:to-spec`, `plan:to-tickets`, and `plan:triage`.

The pointer is a completion criterion, not a suggestion — "the report is unfinished until that pass has run". A step that says *consider running* is a step the agent skips.

## Two modes, and what they are for

`to-ste` routes on what the reader does with the text. **strict** is for text the reader executes: runbooks, acceptance criteria, error messages, reproduction procedures. **flavored** is for text the reader reads: tickets, specs, ADRs, reviews, reports. Flavored keeps richer vocabulary and a longer descriptive sentence, and still bans the slop markers. Every call site names its mode and says why.

All seven chose flavored, which is the honest outcome — every artifact on that list is read rather than executed. `strict` earns its place in `to-ste` for the executable spans inside those artifacts, and for a caller that does not exist yet.

Every call site also names what is **exempt**, because each of these artifacts contains material STE must not touch — code blocks, identifiers, command syntax, log excerpts, stack traces, Mermaid source, the `/dev:codebase-design` glossary terms, and anything quoted from a ticket or a user. Exemptions are per-artifact and stated by the caller; `to-ste` copies every exempt span through untouched.

`jira:ticket` is the instructive case. It is a read-only context bridge, so it gets the pointer only on the branch where it writes the prose deliverable itself, and explicitly not over the context block it assembles from the ticket. Running STE across that block would rewrite the user's own ticket text and silently corrupt the thing the skill exists to deliver faithfully.

## The boundary against `humanize`

`humanize` also strips AI slop, also lives in `general`, and so reaches every department alongside `to-ste`. Two skills with the same symptom list and no stated discriminator is a routing defect, and neither description named one.

They are near-opposites. **`to-ste` removes voice on purpose. `humanize` puts it back.** The routable form of that is one question: does the document carry a **byline**? If a named person will be read as the author — essay, blog post, newsletter, announcement, donor or member communication, marketing copy — that is `humanize`. If the author should be invisible — ticket, spec, ADR, README, runbook, release note, PR description, review — that is `to-ste`. Both descriptions now carry the word and redirect to each other.

## Considered options

- **Merge the two skills.** Rejected on the linter. `to-ste` ends on machine-checkable thresholds, and a well-humanized essay fails them by design: contractions, first person, deliberate fragments, sentence-length variance. In one skill the checkable criterion outranks the fuzzy one, and the agent would grade voice work against a voice-stripping tool. Merging would also make the seven delegating skills load voice material they must never apply.
- **Share a slop-marker reference file between them.** Rejected on measurement: only about six of `humanize`'s 29 tells overlap with STE's rules, and the treatment differs in every case — STE bans and lints, `humanize` offers a rewrite. Coupling two skills for ten lines.
- **Restate the STE rules at each call site** so the caller is self-contained. Rejected as duplication against a single source of truth that would drift seven ways. Call sites name the mode and the exemptions; the rules live in `to-ste`.
- **Wire every skill that emits prose.** Rejected where the artifact argues against it. `research` declined: STE's "one name for one thing" contradicts its rule to preserve the wording of primary sources. `teach` declined: a lesson is not a ticket, spec, ADR, review, or report, and STE would cost it the register it is written in. A wrong pointer is worse than none.

## Consequences

`to-ste` moved from user-invoked to model-invoked, without which none of this works — see [0020](0020-model-invocation-is-a-contract-between-skills.md), which also explains why that promotion follows the house rule rather than bending it.

`general` now carries two de-slopping skills that every department installs, distinguished by a single word in both descriptions. If people route to the wrong one, the discriminator is the thing to fix, not the skill count.

The seven call sites are duplication of a kind: seven sentences that all say "run `/general:to-ste` before delivering". They are cheap and each names its own mode and exemptions, which is the part that cannot be centralised. If an eighth and ninth appear and the sentences start drifting, that is the signal to reconsider.
