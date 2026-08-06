# Credentials come from one file at ~/.claude/passion.env

Every skill that talks to a Passion system reads its credentials from real environment variables first and falls back to a single file at `~/.claude/passion.env`. One file holds Rock, Jira, and whatever comes later. The plugins ship a template; filling it in is the whole setup.

This is not a new invention — `rock_client.py` already resolves credentials this way, environment first and `.env` second. The only change is that the fallback path becomes fixed instead of relative to a repository, because inside a plugin there is no repository to be relative to. A person can be in any directory when they invoke a skill.

`~/.claude/settings.json`'s `env` block was the tempting alternative, and it works: variables declared there reach every tool invocation, which was verified rather than assumed. It would also have made onboarding a single paste, since [0001](0001-public-marketplace-repo.md) already requires editing that file. It was rejected because developers commonly symlink `~/.claude/settings.json` into a dotfiles repository — this machine does exactly that today, into `~/dev/ai` — so secrets placed there are one `git add` from being committed. A separate file at a path no repository reaches removes that failure mode entirely rather than warning about it.

## Considered options

- **Shell profile exports.** Conventional, and needs no code in any skill. Rejected because the filename and syntax differ by shell and operating system, most of this audience has never opened those files, and a GUI-launched session may not inherit a login shell's exports — a failure that looks identical to a wrong password.
- **macOS Keychain or the 1Password CLI.** Much better secret hygiene: nothing in plaintext, ever. Rejected as a baseline because it requires either macOS for everyone or the same password manager installed for everyone. Nothing here prevents an individual from exporting from Keychain into their environment, since real environment variables take precedence.
- **A plugin manifest's `userConfig`.** Found later and worth recording, because it is the mechanism Claude Code provides for exactly this problem and it is better than this decision on almost every axis: values are prompted at enable time, validated against a schema, and anything marked `sensitive` goes to keychain or a credentials file rather than `settings.json` — cross-platform, with no file for anyone to create. It was still rejected, on one clause: sensitive values are exposed only to hook commands and MCP/LSP server configuration, never to skill or agent content. `rock` and `jira` are skills that shell out to Python, so they cannot read them. Taking it would mean either rewriting both as MCP servers or adding a hook that writes the secret back to disk in plaintext — which arrives where we already are, with more moving parts. Non-sensitive values *are* available in skill content, so a split is possible, but two credential mechanisms to save four lines of a file is a bad trade. If `rock` ever becomes an MCP server, revisit this first.

## Consequences

`~/.claude/passion.env` holds plaintext secrets and should be `chmod 600`. It is outside every repository, but it is still a file on a laptop.

Two scripts change. `rock_client.py`'s `_load_env()` points at the fixed path instead of a repository root. `fetch_ticket.py` gains the same fallback — it currently reads bare environment variables with no fallback at all, which is why the jira skill documents `set -a && source .env && set +a` as part of its invocation. That prefix goes away.

`.env.example` cannot be carried over as-is. It contains our Rock and Atlassian hostnames, and [0001](0001-public-marketplace-repo.md) forbids committing those. The shipped template names variables and leaves values blank.

Because the fallback is a fixed absolute path, a skill cannot be tested against a second Rock instance by changing directories. Setting the variables in the environment overrides the file, which is the escape hatch.
