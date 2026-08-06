# Onboarding

**This document is instructions for Claude Code.** A person has asked you to
set them up with the Passion tech skills and named their department. Work
through the six steps below with them.

If you are the person rather than the agent: everything here is doable by hand,
and step 1 is the only part that is fiddly.

---

## Before you start

Confirm the department. It must be exactly one of:

`global-engineering` · `local-engineering` · `ops` · `analytics` ·
`service-and-support`

If they said something else — "engineering", "support", "I'm on the data
team" — ask which of the five, and offer your best guess. Do not pick for
them silently. Installing the wrong bundle is not harmful, just wrong, and it
is corrected by editing one string.

---

## If they already have it

Check before you change anything:

```bash
claude plugin list
```

Compare the result against the table in step 2.

- **Nothing from `passion-tech`.** Start at step 1.
- **Every plugin reads `✔ enabled`, and the count matches.** Say so and stop.
- **Fewer plugins than the table, or one reads `✘ failed to load`.** Go straight
  to step 2. Step 1 has nothing left to do.

---

## Step 1 — Merge two keys into `~/.claude/settings.json`

This is the whole install. Two keys, `extraKnownMarketplaces` and
`enabledPlugins`.

Read the existing file first. It may not exist; it may contain a great deal. Do
not overwrite it, do not reformat it, and do not touch any other key.

**Merge in** (substituting the department for `local-engineering`):

```json
{
  "extraKnownMarketplaces": {
    "passion-tech": {
      "source": { "source": "github", "repo": "passiondev/tech-skills" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "local-engineering@passion-tech": true
  }
}
```

Rules for the merge:

- If either key is absent, add it.
- If either key is present, add the entry **inside** it. Keep every existing
  marketplace and every existing enabled plugin.
- If `passion-tech` or the department key is already there, this step is done —
  say so and move on.
- Nothing else in the file changes.

Show the person the diff before you write it. If the file exists and does not
parse as JSON, stop and tell them — do not guess at a repair.

Exactly one department bundle is needed. It pulls in everything else through
its dependencies; there is nothing else to enable.

This step makes the bundle *enabled* and turns auto-update on. It does not
reliably put the plugins on disk — that is step 2, and skipping it is the one
way to end up half-installed.

---

## Step 2 — Install the bundle

Two commands, in this order.

```bash
claude plugin marketplace add passiondev/tech-skills
claude plugin install <department>@passion-tech
```

The first one fetches the marketplace. Step 1 only *declared* it, and until it
has been fetched the second command fails with `Plugin "<department>" not found
in marketplace "passion-tech"` — so running them out of order looks like a
missing plugin when nothing is missing. Because `passion-tech` is already in
`settings.json`, the add reports `(declared in user settings)` and changes
nothing there.

The second one installs. Then check what landed:

```bash
claude plugin list
```

Every plugin must read `✔ enabled`. If the bundle reads `✘ failed to load`
with a message naming a dependency, run the command in that message and list
again.

Do not skip this in favour of restarting. Enabling a bundle in `settings.json`
does not dependably install the capability plugins it depends on: a startup can
install the bundle and stop, leaving it permanently `✘ failed to load` on a
missing dependency, and further restarts do not repair it. `claude plugin
install` resolves the whole dependency closure in one pass, so it is what makes
this install deterministic rather than lucky.

Expected counts, all skills present:

| Department | Plugins | Skills |
| --- | ---: | ---: |
| `global-engineering` | 5 | 23 |
| `local-engineering` | 7 | 31 |
| `ops` | 4 | 15 |
| `analytics` | 6 | 28 |
| `service-and-support` | 4 | 15 |

Plugin counts include the department bundle itself, which holds no skills.

---

## Step 3 — Check for `uv`

Only needed for `local-engineering`, `analytics`, and `service-and-support` —
the departments with Rock. Skip it otherwise.

```bash
command -v uv
```

If missing, offer the install and let them choose:

```
macOS / Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
Windows:        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
Homebrew:       brew install uv
```

`uv` brings its own Python. Nothing else is required. Do not run the installer
without asking.

---

## Step 4 — Write `~/.claude/passion.env`

Everyone needs Jira. Rock departments also need Rock.

Getting a Jira API token is a task for the person, not for you:

1. Open https://id.atlassian.com/manage/api-tokens
2. **Create API token**, name it something like `claude-code`
3. Copy it — it is shown once

Then write the file. If it already exists, **read it first and merge**; someone
may already have values in there.

```
JIRA_BASE_URL=https://yoursite.atlassian.net
JIRA_EMAIL=you@example.org
JIRA_API_TOKEN=...
JIRA_PROJECT=ABC
```

Rock departments add:

```
ROCK_BASE_URL=https://your-rock-instance
ROCK_USERNAME=...
ROCK_PASSWORD=...
```

Ask for the Rock URL rather than guessing it. If they do not know it or do not
have a Rock account, leave those three blank and tell them the Rock skills will
name what is missing when they first use one. Everything else still works.

Then `chmod 600 ~/.claude/passion.env`.

**Never** put any of these values anywhere else. Not in a repo, not in
`settings.json`, not in a shell profile that lives in a dotfiles repo. That
path is the only place they go. Do not read the token back to them in the
conversation.

---

## Step 5 — Restart and verify

Plugins load at startup, so they need to restart Claude Code. Step 2 put them on
disk; this is what makes their skills available.

Afterwards, a live check — `/jira:sprint` if they gave a project key, or ask
Claude to look up any ticket by key. The counts were already confirmed in step
2, so this is checking that credentials work, not that plugins installed.

For Rock departments, the first Rock command installs the Python runtime into
`~/.claude/passion-rock`. That takes a few seconds once, and is silent after.

---

## Step 6 — Tell them what they have

Point them at the README's skill list for their department, and make these four
points:

- Skills are invoked `/plugin:skill` — `/dev:tdd`, `/rock:find` — or Claude
  reaches for them on its own when they fit.
- Everything updates itself at startup. There is nothing to pull.
- Their credentials live in `~/.claude/passion.env` and nowhere else.
- The marketplace repo is public, so nothing internal is ever committed to it.

---

## If it did not work

| Symptom | Cause |
| --- | --- |
| `claude plugin list` shows nothing new | Claude Code was not restarted, or `settings.json` did not parse |
| `Plugin "<department>" not found in marketplace` | The marketplace has not been fetched. Run step 2's first command, then the second |
| `ENOENT: no such file or directory, mkdir '.../.claude/plugins/marketplaces'` | `~/.claude/plugins` is missing or is a symlink whose target does not exist — common if their dotfiles symlink `~/.claude`. `ls -ld ~/.claude/plugins` shows which. Create the target directory, then re-run step 2 |
| Bundle reads `✘ failed to load`, naming a dependency | Step 2 was skipped or half-finished. Run the `claude plugin install` command in the error, then list again. Restarting does **not** fix this |
| Fewer plugins listed than step 2's table | Same cause — the settings-driven install stopped early. Re-run step 2 |
| Plugin listed, skills not available | Restart came before the fetch — restart again |
| Plugins are behind `main`, or a skill looks out of date | A startup was missed, or Claude Code only ran headless — `claude -p` does not auto-update. Run `claude plugin marketplace update passion-tech`. To read the commit they are on: `git -C ~/.claude/plugins/marketplaces/passion-tech log --oneline -1` |
| A skill says a variable is missing | It names the variable and the file; add it to `~/.claude/passion.env` |
| Rock says `uv` is not installed | Step 3 |
| Jira returns 401 | The token was pasted with a truncation, or `JIRA_EMAIL` is not the address that owns it |

Check `~/.claude/settings.json` parses, and that the department key reads
exactly `<department>@passion-tech`.
