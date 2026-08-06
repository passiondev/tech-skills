# Plugins carry no version numbers

No plugin declares a `version`. Only `name` is required in a manifest, and that is all most of ours will have. Whatever is on main is what everyone's next auto-update installs.

That is the behaviour [0001](0001-public-marketplace-repo.md) was built for. Auto-update for everyone was the hard requirement; versions exist to let people *not* be on the latest, which is the opposite of the goal. Every mechanism versions unlock — pinning, rollback, dependency constraints — assumes someone benefits from lagging behind, and here nobody does.

The cost of the alternative is concrete. `/plugin tag` creates `{name}--v{version}` git tags and validates that `plugin.json` and the enclosing marketplace entry agree, so a version lives in two places for each of ten manifests. Dependency version constraints are the one feature that genuinely requires the tags, and they buy nothing here: every plugin lives in this repo, so they all move together by construction. A constraint between them could never be violated.

## Consequences

A bad commit is live for everyone on their next auto-update, and the only way back is another commit. Nobody can pin, and nobody can roll themselves back. Whatever review discipline this repo adopts is therefore the only safety mechanism it has — there is no second line.

The `/plugin` interface has no version to display for these plugins, so a person cannot tell what they are running beyond "whatever main was at their last update," and cannot report it in a bug report. The git SHA of the marketplace checkout is the real answer, but nothing surfaces it.

Adding versions later is straightforward — add the field, start tagging. Removing them once people depend on constraints is not, which is the asymmetry that makes starting without them the cheaper mistake to make.
