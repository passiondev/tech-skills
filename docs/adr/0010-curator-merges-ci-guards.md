# One curator merges; CI enforces what a reviewer would miss

Main is protected and takes changes only through pull requests. `CODEOWNERS` assigns everything to the curator, who reviews and merges. CI runs on every pull request and fails it on anything that would leak, break, or contaminate.

*That first sentence was aspirational for this repo's entire pre-publication life. `main` had no protection and no ruleset until the day the repo was published, and five people held admin on it — so the sentence described an intention as a fact, which is the most expensive kind of documentation error. `CODEOWNERS` cannot require anything on its own; without a ruleset it only annotates a pull request with a name. And because `check.yml` triggers on `push` to `main` as well as on pull requests, CI was running **after** the change was already live for everyone. It reported; it did not gate. The ruleset now requires a pull request and a green `check` before anything reaches `main`, and blocks force-pushes and deletion. It was negative-tested by pushing an empty commit directly and confirming both rules rejected it.*

*Two details follow from the single-curator model. `bypass_actors` is empty, which honours the option rejected below rather than quietly adopting it — the curator's own changes go through the same gate. And required approvals is **zero**, because GitHub forbids approving your own pull request and a stricter setting would lock the sole curator out of the repo. So the enforced gate is "a pull request that passed CI", not "a second pair of eyes"; `CODEOWNERS` stays advisory until there is more than one reviewer. Per-department `CODEOWNERS` below is the growth path, and it is what makes review mechanically enforceable.*

Two earlier decisions made this necessary rather than merely tidy. [0009](0009-no-plugin-versions.md) removed versions, so a merge is live for everyone on their next auto-update and the only way back is another commit — review is not one safety mechanism among several, it is the only one. And [0001](0001-public-marketplace-repo.md)'s rule that nothing internal may be committed has, so far, been enforced by nothing at all.

The division of labour is deliberate. A human reviewer is good at judging whether a skill is any good and bad at spotting a hostname in the two-hundredth line of a diff. So the machine takes the mechanical checks: manifests parse, every `source` path in `marketplace.json` exists, every dependency resolves to a plugin that is actually present, no contaminated skill name appears in the tree, and no string matching our hostnames or a credential shape is committed. The curator judges the content.

The GitHub plan happened to cooperate. `passiondev` is on the Free plan, where branch protection is available for public repositories only. Had [0001](0001-public-marketplace-repo.md) gone the other way, there would have been no way to require review at all without paying for it.

## Considered options

- **Per-department `CODEOWNERS`.** Each capability plugin owned by someone who knows the domain — Rock to whoever runs Rock, `dev` to an engineer — with the marketplace manifest and the department bundles kept centrally. The reviewer would actually understand what they were approving, and review would scale past one person. This is the growth path, deferred only because it needs reviewers who have agreed to review, and because widening who can ship to thirty people is not something to do before the first version exists.
- **Direct push for the curator, pull requests for everyone else.** Fastest loop, no ceremony for the person doing nearly all the work. Rejected because it exempts the path that will produce almost every change from the only safety mechanism the project has.

## Consequences

One reviewer is a bottleneck the moment they are on holiday, and there is no second approver. That is acceptable at current volume and is the first thing to revisit.

The CI leak check is a denylist, and denylists only catch what they were told about. It will catch our two known hostnames and the seven contaminated skill names. It will not catch a new internal system mentioned for the first time, or a real person's record pasted into a skill as an example. The check reduces the human's load; it does not replace their judgement.

Enforcement is only as good as the branch protection settings, which live in GitHub rather than in this repo. Nothing here fails if someone with admin rights turns them off.
