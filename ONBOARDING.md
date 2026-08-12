# Onboarding

**This document is instructions for Claude Code.** Someone has asked to be set
up with the Passion tech skills and named their department. You do the install.
They approve what you run, answer a handful of questions, make one trip to
Atlassian, and type one command themselves.

Assume they are not a developer. Some of them are — the ones who need this
document most are not, and the failure it exists to prevent is a person
concluding halfway through that they have broken their computer.

If you are the person rather than the agent: all of this is doable by hand, and
step 3 is the whole install. It is two commands.

---

## How to run this

Seven steps. Do one, say what happened in a sentence or two, say what is next,
then stop and let them answer. The temptation is to run four steps in one turn
because nothing prevents you; resist it. Someone watching output scroll past has
no idea which part they are meant to react to, and that is where the fear comes
from.

Open by telling them the shape of it: seven steps, about ten minutes, and the
only part that is real work is one visit to Atlassian to make a token.

How to talk to them:

- **One thing to do at a time.** Never a command and a website in the same
  message. Never two commands.
- **No jargon.** "The settings file Claude Code reads when it starts", not
  "user-scope `settings.json`". "Your Jira web address", not "base URL". Where
  you have to name a real path, say what it is in the same sentence.
- **Say what you are about to do before you do it.** The approval prompts land
  in the middle of your turn. Someone who was told what was coming reads them as
  expected; someone who was not reads them as a warning.
- **Never repeat a secret back.** Not the Jira token, not a Rock password, not
  to confirm you read it right. Say you have it and move on.
- **Their errors are your problem.** When a command fails, say in one sentence
  what it means and what you are doing about it. Do not paste the output and
  wait.

---

## Before you start — the department

Confirm it. It must be exactly one of:

`global-engineering` · `local-engineering` · `ops` · `analytics` ·
`service-and-support`

If they said something else — "engineering", "support", "I'm on the data team" —
ask which of the five and offer your best guess. Do not pick for them silently.
The wrong bundle is not harmful, just wrong, and it is corrected by re-running
step 3 with the right name.

---

## Step 1 — What is about to happen, and why Claude keeps asking

Before you touch anything, tell them two things. This step is entirely talking.

**First, what you are going to do.** Four things: install their department's
skills, turn on automatic updates, help them make a Jira token and save it, and
switch the new skills on. Nothing here touches their code, their repositories,
or anything they have open.

**Second, the permission prompts.** They are about to see the first one, and
this is the single thing most likely to worry them. Explain it before it
appears, in roughly these words:

> Claude Code asks before it changes a file or runs a command on your machine.
> You will see a box with a few choices. That is it working correctly — nothing
> has gone wrong, and nothing runs until you pick.
>
> - **Yes** — do it this once.
> - **Yes, and don't ask again** — remember this kind of command so you stop
>   being asked for it.
> - **No** — decline. You can type what you would rather I did instead.
>
> Escape always interrupts, at any point, including mid-command.
>
> When the prompt is about a command rather than a file, **Ctrl+E** explains what
> the command actually does and rates it low, medium, or high risk before you
> decide.
>
> You will see about six of these during setup. I will say what each one is for
> before it appears.

Then do exactly that for the rest of the conversation. "I am going to run
`claude plugin list`, which just reads what you already have — you will get a
prompt" costs one sentence and removes the whole problem.

**If they ask how to stop being asked**, or you can see the prompts wearing on
them, the honest answer is the permission mode. `Shift+Tab` cycles it and the
current mode shows at the bottom of the screen. Auto mode is the one worth
naming: a second model checks each action against what they asked for and blocks
anything that goes beyond it, so the prompts mostly stop without the safety net
going with them. From 14 August 2026 it is the default for new sessions on Pro,
Max, and Team plans, so many people will already be in it and will never see the
prompts this step describes. Say so and move on rather than re-explaining.

**`--dangerously-skip-permissions` will come up**, because somebody will have
mentioned it. Answer plainly and briefly: it turns the checks off completely,
it is built for throwaway containers rather than the laptop with their email on
it, and it cannot be switched on part-way through a session anyway. Do not
suggest it and do not run it. Setup needs about six approvals in total, which is
not a problem worth that. If they want it regardless, it is their machine —
say where the risk sits and let them decide.

---

## Step 2 — Check what they already have

Tell them this one only reads. Then:

```bash
claude plugin list
```

Read the output for three things: whether anything is named `@passion-tech`,
whether each of those says `Status: ✔ enabled`, and whether each says
`Scope: user`.

| What you see | What it means | Where to go |
| --- | --- | --- |
| Nothing named `@passion-tech` | Not installed | Step 3 |
| Everything `✔ enabled`, every `Scope: user`, count matches step 3's table | Fully installed | Say so, then carry on from step 4 — a bundle with no credentials is still half a setup |
| Any `Scope: project` or `Scope: local` | Installed for one folder only. This is why skills work in one project and nowhere else | Clear that scope, then step 3 |
| Fewer plugins than the table, or any `✘ failed to load` | A half-finished install | Step 3, which repairs it |

To clear a wrong scope before reinstalling, name the department bundle and the
scope you actually saw. `--prune` takes its capability plugins with it:

```bash
claude plugin uninstall <department>@passion-tech --scope <project|local> --prune -y
```

---

## Step 3 — Install

Two commands, in this order. Run them one at a time and say what each is for.

```bash
claude plugin marketplace add passiondev/tech-skills
```

This fetches the catalogue. It takes a few seconds and clones over SSH, falling
back to HTTPS on its own if they have no GitHub key — either way it works, and
the retry line it prints is not an error.

```bash
claude plugin install <department>@passion-tech --scope user
```

This installs. It reports the bundle plus the capability plugins it pulled in —
`+ 3 dependencies: general, plan, jira` for `ops`, and so on. One command does
the whole dependency closure; there is nothing else to install.

`--scope user` is already the default, so write it anyway. It is the difference
between skills that work in every folder and skills that work in one, it costs
nothing to be explicit, and being explicit is what stops a future version or a
stray flag from quietly changing the answer.

The order matters. `marketplace add` first, because until the catalogue has been
fetched the install fails with `Plugin "<department>" not found in marketplace
"passion-tech"` — which reads like a missing plugin when nothing is missing.

Then check what landed:

```bash
claude plugin list
```

Every plugin must read `✔ enabled` and `Scope: user`, and the count must match:

| Department | Plugins | Skills |
| --- | ---: | ---: |
| `global-engineering` | 5 | 23 |
| `local-engineering` | 7 | 31 |
| `ops` | 4 | 15 |
| `analytics` | 6 | 28 |
| `service-and-support` | 4 | 15 |

Plugin counts include the department bundle itself, which holds no skills.

Do not try to do this by editing settings instead. Enabling a bundle in
`settings.json` does not dependably install what it depends on: a startup can
install the bundle and stop, leaving it permanently `✘ failed to load` on a
missing dependency, and further restarts do not repair it.

**Then turn on auto-update.** `marketplace add` writes the marketplace into
`~/.claude/settings.json` — the settings file Claude Code reads when it starts —
but leaves auto-update off, because third-party marketplaces default to off.
That one flag is what keeps everyone current, so add it.

Read the file, find the `passion-tech` entry that the previous command wrote,
and add one key inside it. This is what that entry should read afterwards:

```json
{
  "extraKnownMarketplaces": {
    "passion-tech": {
      "source": { "source": "github", "repo": "passiondev/tech-skills" },
      "autoUpdate": true
    }
  }
}
```

**That is one added line, not a file to paste.** The entry is already there
bar the `autoUpdate` line; the outer braces are shown so the example parses, not
because the file contains only this. Their settings file will have other keys in
it, and every one of them stays.

Show them the added line before you write it. Change nothing else — not the
formatting, not another key, and not `enabledPlugins`, which the install has
already filled in with every dependency. If the file does not parse as JSON,
stop and tell them rather than guessing at a repair.

---

## Step 4 — Check for `uv`

Only for `local-engineering`, `analytics`, and `service-and-support` — the
departments with Rock. Skip it otherwise, and say you are skipping it.

```bash
command -v uv
```

If it is missing, say what it is in one line — the thing the Rock skills run on,
and it brings its own Python — then offer the three ways and let them pick:

```
macOS / Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
Windows:        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
Homebrew:       brew install uv
```

Do not run an installer without asking.

---

## Step 5 — Credentials

Everyone needs Jira. Rock departments also need Rock. All of it goes in one
file, `~/.claude/passion.env`, which lives in their home folder and never in a
repository.

Do this as a conversation, not a form. Ask for the values you still need, a
couple at a time, and say where each one is found.

### The three they can read off the screen

Ask them to open Jira in a browser tab first — all three are in front of them
once it is open.

1. **The web address.** The address bar reads
   `https://yoursite.atlassian.net/...`. Everything up to and including
   `.atlassian.net` is the value. This is `JIRA_BASE_URL`.
2. **Their email.** The one they sign in to Jira with. It has to be the account
   that owns the token, or the token will be rejected. This is `JIRA_EMAIL`.
3. **The project key.** Open any ticket in the project they work in. The key is
   the letters before the number — a ticket called `ABC-123` means the key is
   `ABC`. This is `JIRA_PROJECT`.

### The token

This is the one part that happens on a website instead of in here, and the one
part you cannot do for them. Walk it one instruction per message.

1. Open **https://id.atlassian.com/manage-profile/security/api-tokens**. Say
   what it is before they click: Atlassian's own account page, and it will ask
   them to sign in.
2. Click **Create API token**. If they are offered **Create API token with
   scopes** as well, that is the wrong one — the plain one is what these skills
   use.
3. Name it something they will recognise in a year — `claude-code` is fine. The
   name is only a label.
4. Pick an expiry. Anything up to 365 days; Atlassian defaults to a year. Tell
   them plainly that it stops working on that date and they come back to this
   page and make another. There is no renewal.
5. Click **Create**, then **Copy**.
6. Paste it into the chat.

Before they paste, tell them what you will do with it: write it to the file, and
never repeat it back. Then do exactly that. Do not echo it, do not read it back
to confirm, do not print the file afterwards.

Say once, in plain words, that the token is a password for their Atlassian
account. It goes in that one file and nowhere else — not in a repository, not in
the settings file, not in a shell profile that syncs somewhere.

### Rock, for the departments that have it

Ask for the Rock web address rather than guessing it, plus their username and
password. If they do not know the address or do not have a Rock account, leave
those three blank and tell them the Rock skills will name exactly what is
missing the first time they use one. Everything else still works.

### Writing the file

If `~/.claude/passion.env` already exists, read it first and merge — someone may
have values in there already. Otherwise write it fresh:

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

Then `chmod 600 ~/.claude/passion.env`, and say what that did in six words: only
their account can read it.

---

## Step 6 — Switch the skills on, without restarting

The plugins are on disk now, but this session loaded its list of skills when it
started, so it cannot see them yet. It does **not** need restarting. One command
refreshes it in place and the conversation carries on.

You cannot run this one — it is a Claude Code command rather than a shell
command, so it has to be typed at the same prompt they type messages at. Ask
them to type exactly:

```
/reload-plugins
```

Say two things first, because both look like failures and neither is:

- The summary it prints counts skills from a plugin's `commands/` folder. Every
  Passion skill lives in `skills/` instead, so it will say **0 skills** while
  having loaded all of them. Ignore that number; the plugin count is the real
  one.
- If it warns that reloading would make it re-read the conversation and stops
  without doing anything, ask them to run `/reload-plugins --force`.

Once it has run, the new skills are available to you in this same session — no
restart, nothing lost. Confirm that out loud, because the last thing they heard
about plugins was probably that they need a restart.

**Then use one for real.** This checks the credentials, which is the part that
has not been tested yet; the plugin count was already confirmed in step 3.

- If they gave a project key, run `/jira:sprint` and show them their own queue.
- If they did not, ask for any ticket key they can think of and fetch it.
- For Rock departments, `/rock:status` checks the connection. The first Rock
  command installs a small Python runtime into `~/.claude/passion-rock`, which
  takes a few seconds once and is silent afterwards. Say so before it happens.

If a credential is wrong, the skill says which variable and which file. Fix it
and run the skill again — still no restart.

---

## Step 7 — Leave them something to keep

Write a short reference to their machine and open it, so that the answers are
somewhere other than a chat log they will close.

Put it at `~/Documents/passion-claude-code.md`, or in their home folder if there
is no `Documents`. Then open it in VS Code:

```bash
code ~/Documents/passion-claude-code.md
```

If `code` is not found, VS Code's command line helper is not installed. On macOS
try `open -a "Visual Studio Code" ~/Documents/passion-claude-code.md`. If VS Code
is not on the machine at all, do not install anything — tell them where the file
is and leave it there.

Write it for the person, not for an agent. Fill in their department, their
skills, and their project key. Keep it to one screen:

```markdown
# Claude Code at Passion

## When it asks permission
Claude stops and asks before it changes a file or runs a command.
  Yes                     do it this once
  Yes, don't ask again    stop asking for this kind of command
  No                      decline, and say what you'd rather do
Escape interrupts, any time. Ctrl+E explains a command and rates
its risk before you decide.
Fewer interruptions: Shift+Tab cycles the mode, shown at the
bottom of the screen. Auto mode has a second model check each
action instead of asking you.

## Your skills
Type these, or just describe what you want and Claude finds them.
  /jira:sprint     what's assigned to me this sprint
  /jira:ticket     pull up ABC-123 and work from it
  ...one line per skill they will actually use...

## Where things live
  ~/.claude/passion.env    your Jira and Rock logins. Nowhere else.
Your Jira token expires — Atlassian emails you. Make a new one at
id.atlassian.com, same page, and tell Claude to update the file.

## If a skill goes missing
  /reload-plugins          reloads without restarting
Skills update themselves when you start Claude Code. Nothing to pull.

## The full list
github.com/passiondev/tech-skills
```

Then say three things and stop:

- Skills fire on their own when they fit. Typing `/plugin:skill` forces one.
- Everything updates itself at startup. There is nothing to pull, and a skill
  can change under them.
- Their credentials are in that one file and nowhere else.

Offer to run one more skill on something real they mentioned. A skill used once
in the conversation that introduced it is worth more than the whole list
described perfectly.

---

## If it did not work

| Symptom | Cause |
| --- | --- |
| Skills work in one folder and nowhere else | They were installed at project or local scope. `claude plugin list` shows `Scope:` per plugin — anything not `user` is the cause. Uninstall at that scope and re-run step 3 with `--scope user` |
| `claude plugin list` shows nothing new | The install did not run, or `~/.claude/settings.json` does not parse |
| `Plugin "<department>" not found in marketplace` | The catalogue has not been fetched. Run step 3's first command, then the second |
| `ENOENT: no such file or directory, mkdir '.../.claude/plugins/marketplaces'` | `~/.claude/plugins` is missing, or is a symlink whose target does not exist — common where dotfiles symlink `~/.claude`. `ls -ld ~/.claude/plugins` shows which. Create the target directory, then re-run step 3 |
| Bundle reads `✘ failed to load`, naming a dependency | The install stopped early, or settings were edited in place of running it. `claude plugin install` resolves the whole dependency closure in one pass; restarting does **not** repair this |
| Fewer plugins listed than step 3's table | Same cause. Re-run step 3 |
| Plugins installed, skills still not available | `/reload-plugins` has not been run in this session, or it warned and stopped — run `/reload-plugins --force` |
| `/reload-plugins` reports `0 skills` | Expected. It counts only `commands/` folders, and every Passion skill lives in `skills/`. The plugin count is the one to read |
| Plugins are behind `main`, or a skill looks out of date | A startup was missed, auto-update was never turned on (step 3), or Claude Code only ran headless — `claude -p` does not auto-update. Update each plugin, then restart: `claude plugin list \| grep -o '[a-z-]*@passion-tech' \| sort -u \| xargs -n1 claude plugin update`. `claude plugin marketplace update` will not do it — it moves the marketplace clone and leaves the installed plugins behind. The version beside each entry in `claude plugin list` is what that plugin is running |
| A skill says a variable is missing | It names the variable and the file. Add it to `~/.claude/passion.env` |
| Rock says `uv` is not installed | Step 4 |
| Jira returns 401 | The token was truncated when pasted, it has passed its expiry date, or `JIRA_EMAIL` is not the address that owns it |

Check that `~/.claude/settings.json` parses, and that the department key under
`enabledPlugins` reads exactly `<department>@passion-tech`.
