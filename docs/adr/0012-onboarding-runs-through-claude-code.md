# Onboarding runs through Claude Code itself

Setup is one sentence pasted into Claude Code — the person's department plus a link to `ONBOARDING.md` in this repo. Claude reads the document, merges the settings into whatever `~/.claude/settings.json` already exists, walks the person through obtaining a Jira API token, writes `~/.claude/passion.env`, and checks for `uv`.

The whole install reduces to two keys in one file:

```json
{
  "extraKnownMarketplaces": {
    "passion-tech": {
      "source": { "source": "github", "repo": "passiondev/tech-skills" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": { "local-engineering@passion-tech": true }
}
```

`autoUpdate` is documented as updating "this marketplace and its installed plugins on startup", so one flag delivers what [0001](0001-public-marketplace-repo.md) required. `enabledPlugins` takes `plugin@marketplace` keys, and [0002](0002-capability-plugins-and-department-bundles.md)'s dependency mechanism does the rest — naming the department bundle pulls in every capability plugin it needs.

Everyone installing this has Claude Code, by definition. That makes the agent the one tool the entire audience is guaranteed to have, on any operating system, with no script to write or keep working. And the actual difficulty here is merging two keys into a file that may or may not exist and may already contain anything — which is precisely what a copy-paste instruction handles badly and an agent handles well. Claude shows the diff before writing, so the person still sees what changed.

It also covers the parts a JSON block cannot. Getting a Jira API token means visiting Atlassian and creating one; `uv` may not be installed; `passion.env` needs six values a person has to gather. Those are an interview, not a paste.

## Considered options

- **Five copy-paste blocks in the README, one per department.** Transparent, nothing to maintain, nothing executed that was not read. Rejected on the known failure mode: someone with an existing `settings.json` replaces it rather than merging, or leaves a trailing comma, and it surfaces much later as "the plugin didn't install" with no visible cause. The block stays in `ONBOARDING.md` for anyone who prefers it — it is what Claude will be reading anyway.
- **An install script.** Deterministic and testable, which neither other option is. Rejected because it needs a PowerShell twin for anyone on Windows, and because it asks people to pipe a remote script into a shell — or to read it first, which is the step that gets skipped.

## Consequences

`ONBOARDING.md` is now executable documentation. It is read by an agent that will act on it, so vagueness there becomes wrong actions on someone's machine. It needs to state exactly which keys to merge and exactly what to leave alone.

Nothing about this is deterministic. Two people can run the same sentence and get different conversations, and there is no way to test the path the way a script could be tested. The mitigation is that the resulting state is checkable — `claude plugin list` shows what landed.

The instruction includes a public URL, so it depends on the person's Claude Code being able to fetch it. Where it cannot, the document has to be pasted instead.
