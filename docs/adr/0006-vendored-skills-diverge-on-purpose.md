# Vendored skills are copied once and then diverge on purpose

The skills coming from `~/dev/ai` are copied into this repo, and this repo owns its copies. `~/dev/ai` stays a personal working set feeding seven harnesses. There is no sync step and no promotion step, because the two are allowed — expected — to drift apart.

That is the opposite of the call made for the Rock client in [0004](0004-tech-skills-owns-the-rock-client.md), and the difference is what the copies are for. There was one audience for the Rock client, so two copies of it were pure liability. Here there are two audiences. A Passion `code-review` can know that our tracker is Jira and what our label vocabulary means; a personal one has to stay generic to be useful in any repo. Treating that difference as drift to be suppressed would make both versions worse.

The tax is low because of what these files are. They are prose, not code under daily churn — most are a few kilobytes and change rarely. A fix that genuinely belongs in both places gets made twice, occasionally.

Every vendored skill records where it came from. That is not bookkeeping for its own sake: several of these derive from `mattpocock/skills`, which is MIT and therefore requires attribution. Recording provenance uniformly means the licence obligation is met by the same mechanism that lets us diff against origin when we want to.

## Considered options

- **`~/dev/ai` stays canonical, changes promoted here.** One editing surface, all seven harnesses current. Rejected because the team could then never fix a skill directly — every improvement would have to route through a personal repository first — and the public copy would always lag by however long passes between promotions.
- **Point `marketplace.json` at `justinpbarnett/ai` with a `github` source.** Zero copies, so nothing can drift, and it would work today since that repo is already public. Rejected because the tech team's tooling would depend on one person's personal account, and the seven contaminated skills live in that same tree with nothing structural keeping them out of what we publish.
- **This repo canonical, with `~/dev/ai` symlinked into it.** One copy, owned by the team, current everywhere. Rejected because it is the arrangement that produced the contamination: `harnesses.toml` records Cursor writing its own built-ins through such a symlink into the shared skills directory, from where they propagated to every harness. Aiming that at a public Passion repository makes the same accident publish itself.

## Consequences

`justinpbarnett/ai` is public and has no `LICENSE` file, so MIT-derived skills are already being redistributed there without attribution. Copying them here without fixing that would repeat the problem in the team's name. This repo needs a licence and an attribution file before those skills land.

Seven skills are excluded as contamination and must never be copied: `help`, `imagine`, `check-work`, and `create-skill` arrived from another harness's built-ins; `docx`, `pptx`, and `xlsx` are Anthropic-proprietary and not redistributable. All seven are untracked in `~/dev/ai`, which is the tell — a `git ls-files` check is a reliable filter, and `to-ste` is the one untracked skill that is genuinely authored rather than contamination.

`setup-matt-pocock-skills` cannot be dropped despite the name. Five skills — `wayfinder`, `to-tickets`, `code-review`, `to-spec`, `triage` — expect `docs/agents/issue-tracker.md` to exist and instruct the user to run it when it is missing. Since we own our copies now, that skill can be renamed and its per-repo configuration step can be reconsidered, given that our tracker is known in advance.
