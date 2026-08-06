# Model invocation is a contract between skills

`disable-model-invocation: true` hides a skill from the model. The model is also what runs other skills, so the flag hides it from them too. A skill body that says "invoke `to-spec`" is therefore giving the agent an instruction it cannot carry out — and nothing in the repo noticed, because the sentence is spelled correctly and points somewhere the reader has installed.

Call it a **dead handoff**. Three of them were live in the marketplace. [0017](0017-skill-pointers-carry-their-namespace.md)'s `cross-references` check could not see any of them: it verifies that a pointer resolves and that the department installing the caller also installs the target. Both were true in all three cases. Invocability is a third property, and it was unchecked.

## The rule that was already being followed

The split was never written down, but every one of the 31 skills obeys it:

- **user-invoked** — writes outside the conversation (commits, publishes to Jira) or seizes the session for a long interview: `implement`, `to-spec`, `to-tickets`, `triage`, `wayfinder`, `improve-codebase-architecture`, `teach`, `grill-me`, `grill-with-docs`.
- **model-invoked** — reference, analysis, or transformation, the other 22: `tdd`, `code-review`, `codebase-design`, `diagnosing-bugs`, `research`, `prototype`, `grilling`, `resolving-merge-conflicts`, `domain-modeling`, `humanize`, `to-ste`, `onboard`, `ticket`, `sprint`, and the eight Rock and Rock-build skills.

The rule is about *consequence*, not about how useful autonomous firing would be. That is why the fix for a dead handoff is to reword the caller rather than to flip the target: making `implement` model-invoked would give the marketplace its only skill that commits to a branch on its own initiative, and making `to-spec` model-invoked would give it one that publishes to Jira unprompted. Both are precisely what the rule exists to prevent.

`to-ste` was the exception that proved it. It was user-invoked, which made it unreachable by the seven skills that now delegate to it ([0021](0021-technical-writing-goes-through-ste.md)). It transforms a draft held in context and writes nothing outside the conversation, so by the rule above it belonged in the model-invoked column all along. Promoting it was a correction, not a special case.

## Considered options

- **Flip the targets to model-invoked and let the handoffs work as written.** Rejected on consequence, as above. The dead handoffs are a symptom of callers written in the wrong voice, not of the targets being classified wrongly.
- **Leave it to review.** Rejected because the failure is silent in both directions: the agent reads an instruction it cannot follow, and the reader of the skill cannot tell by looking. Three separate skills had it, and one of them acquired it from a sibling by copying the wording.
- **Ban naming a user-invoked skill from another skill's body.** Rejected as too blunt. `onboard` is a catalogue whose whole job is naming skills across the marketplace; `to-spec` cites `/plan:triage` to borrow its role vocabulary, not to run it; `jira:ticket` names `to-spec` and `implement` precisely in order to tell the user to run one. Naming is fine. Instructing the agent to run one is not.

## Consequences

`check.py` gains an `invocability` check — the thirteenth. It reads `disable-model-invocation` from every skill's frontmatter, finds each mention of a user-invoked skill in another skill's body, and fails when an invocation verb governs the reference without naming a person as the runner. It carries an `INVOCABLE_REFS` allowlist with the same self-expiring discipline as `OPTIONAL_REFS`: an entry states why the sentence is safe and fails when the sentence changes or the target's invocation mode does. The allowlist is currently empty, which is the intended steady state.

The check is a heuristic over English, so it will eventually be wrong in both directions. It was tuned against the four real defects this pass found and the legitimate forms already in the repo, and the allowlist absorbs the false positives without weakening the rule.

The callers were reworded rather than the targets reclassified. `jira:ticket` now says `to-spec` and `implement` are user-invoked and names the one that fits for the user to run; `diagnosing-bugs` recommends the user run `/dev:improve-codebase-architecture` and hands them the specifics to paste in. This is constrained by `jira:ticket`'s own rule that you never tell someone to run a skill they do not have — Ops and Service and Support install `jira` without `plan` or `dev` — which is also why those references stay in prose rather than becoming `/plugin:skill` pointers that would fail the reachability check.

One habit was retired along the way. Four skills said "use the `jira` skill", which names nothing invocable: `jira` is a capability plugin holding `ticket` and `sprint`. It looked like an established idiom and was in fact one sentence written once and pasted three times; a fifth copy appeared during this pass, from an agent following the sibling wording. All four now fetch context with `/jira:ticket`.
