# General carries the cross-discipline skills; jira keeps its own namespace

`general` holds the skills anyone at Passion might use regardless of discipline: `teach`, `research`, `handoff`, the grilling family, the two prose skills, and `writing-great-skills`. It also declares `jira` as a dependency rather than absorbing it, so `jira` keeps its own name and reads `/jira:ticket`. Installing `general` still gets both.

`writing-great-skills` was added here after the fact, having fallen through every grouping — it is not a thinking, writing, or learning skill, and it is neither `dev` nor `plan`. It belongs to anyone who wants to add a skill to this marketplace, which under [0010](0010-curator-merges-ci-guards.md) is anyone at all. Thirty-two tokens to make the marketplace self-extending is the cheapest thing in here.

The ticket-authoring cluster stays out of `general`. `to-spec` writes engineering specs, `wayfinder` navigates a ticket graph inside a codebase, `code-review` reviews code — Service and Support and Analytics do none of that, and putting those in front of them invites misuse rather than adoption.

*The claim about Analytics did not survive contact. [0018](0018-the-roster-is-pruned-and-onboard-replaces-the-index.md) gives them `plan` outright: analysts scope work and file tickets like everyone else, and this paragraph contradicted [0008](0008-department-to-capability-mapping.md) giving them `dev` on the grounds that they write code.*

Context cost turned out not to be the deciding factor, contrary to expectation. All twenty-four shippable skills together cost about 1,240 tokens per turn, which is noise. The real currency is legibility: whether every skill a person sees is one they might plausibly use. Worth noting that the seven excluded contaminated skills cost 901 tokens between them and include the two most expensive items in the directory — `xlsx` at 236 tokens and `docx` at 197 — so excluding them saves nearly three times what the entire `general` plugin costs.

Keeping `jira` separate is a deliberate exception to the clean split in [0002](0002-capability-plugins-and-department-bundles.md). A capability plugin may declare dependencies; only the reverse — a bundle holding skills — is ruled out. `jira` earns the exception because it is a Passion system with credentials and a setup step, and because `/jira:ticket` is the name people will type most often in this marketplace. `/general:jira` would have put the ugliest name on the most-used skill.

## Considered options

- **`general` as a pure bundle over `think`, `write`, `learn`, and `jira`.** Every namespace would then carry information: `/think:grilling`, `/write:humanize`. Rejected because it costs five manifests instead of two and scatters a generalist's skills across four prefixes in the picker, which is worse for browsing than clustering them under one — the namespace's job here is grouping, not description.
- **Everything inside `general`, accepting `/general:jira`.** One manifest, nothing to compose. Rejected for the naming cost on the single most-used skill.
- **Ticket workflow in `general` too**, on the grounds that everyone at a church tech team lives in Jira. Still only ~525 tokens. Rejected because taking a ticket is not the same as authoring a spec or walking a repository's ticket graph.

## Consequences

An earlier draft of this ADR claimed `humanize` and `contribute` had descriptions too thin to route to. That was a measurement error — both use YAML folded scalars, and the parser stopped at the `>`. Measured properly, `humanize` is 110 tokens and the second most expensive skill in `general`; `contribute` is 192 and the most expensive skill in the whole set. The thin descriptions are elsewhere and are thin on purpose: `grill-me` at 15 tokens, `teach` at 16, `implement` at 17. Those three route on their names, which is adequate for skills people invoke deliberately.

`general` depends on `jira`, so `jira` can never be disabled while `general` is enabled. That is correct here but means a person who does not use Jira cannot opt out of it without leaving `general`.

*[0018](0018-the-roster-is-pruned-and-onboard-replaces-the-index.md) later dropped `handoff` and `writing-great-skills` from this list and added `onboard`. The paragraph below is why the second removal was easy.*

*Upstream has since renamed `writing-great-skills` to `writing-for-agents`, widened it to cover `AGENTS.md` and `CLAUDE.md`, and made it model-invoked. We kept ours. The thirty-two tokens argued for above are the cost of a `disable-model-invocation: true` skill; the model-invoked version would sit in every person's context on every turn, and the paragraph that admits this skill to `general` stops holding. Worth revisiting if people start writing `AGENTS.md` at Passion — `docs/vendored.json` carries the pointer to upstream's version.*
