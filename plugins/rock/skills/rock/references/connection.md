# Connection, catalog, logs, and screenshots

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" catalog status     # connection, Rock version, catalog age
"$R" catalog refresh    # pull a fresh catalog
"$R" catalog show       # what the cached catalog contains
```

## Setup

Rock needs three variables. Put them in `~/.claude/passion.env`, one per line —
that file is outside every repository, so it cannot be committed:

```
ROCK_BASE_URL=https://your-rock-instance
ROCK_USERNAME=your_rock_login
ROCK_PASSWORD=your_rock_password
```

Real environment variables win over the file if both are set. The client signs in
with `POST /api/Auth/Login` and reuses the session cookie. Ask whoever
administers Rock for the URL and for an account — do not guess the hostname.

**Ask for the narrowest account that does the job.** Rock's permissions are the
only limit on what these tools can change; there is no read-only install to fall
back on. Someone who only ever looks things up should be given an account that
only ever looks things up.

Setup is done when `catalog status` prints a Rock version and a search returns at
least one match:

```bash
"$R" catalog status
"$R" query search "volunteer"
```

## The catalog

The catalog caches Rock's building blocks — action components, block types, field
types, categories, sites — so name-to-ID lookups do not hit the API every time.
Refresh it on first use, after anyone installs a Rock plugin, and when a lookup
fails for something you can see in the Rock UI.

Prefer the catalog over hardcoded IDs. IDs differ between Rock instances, and a
hardcoded one that happens to work today is a bug waiting for a restore.

## Exception logs

```bash
"$R" query exceptions --summary               # grouped by type, with counts
"$R" query exceptions --type "NullReference" --limit 20
"$R" query exception <id> [--json]            # one exception, with stack trace
```

Start with `--summary`: a handful of noisy recurring types dominate the log and
bury anything new in a raw list. Compare counts and first-seen dates before
concluding anything is new.

`--verbose` adds stack traces to the list, and is only useful once you have
narrowed to a type. Deleting exception logs is a write — `exception-clear` in
`references/writing.md`.

## The browser tooling is opt-in

Screenshots and page verification need Playwright — a ~150 MB Chromium download,
not installed by default. To add it:

```bash
ROCK_WITH_BROWSER=1 "$R" catalog status   # installs Playwright and Chromium, once
"$R" browser login                        # confirm it can sign in
"$R" browser screenshot /volunteers
"$R" browser verify-page 412              # does the page load without errors
"$R" browser check-element /volunteers ".signup-form"
```

The flag is needed once. The choice is remembered, so every later command keeps
the browser and a plain command never removes it.

Add `--headed` to watch it. Screenshots stay out of every repository, because a
screenshot of a Rock page is full of real people's names.

## Where things live

Everything the runtime writes is under `~/.claude/passion-rock`:

| | |
| --- | --- |
| `.venv/` | the Python environment |
| `catalog.json` | the cached catalog |
| `rock.log` | every API call and command — 2 MB rotating, 3 backups |
| `screenshots/` | anything the browser tooling captured |
| `snapshots/` | the entity a `PUT` replaced, written before the request went |
| `.browser` | present once you opted into the browser tooling. Delete it and the next command re-syncs without Playwright |

This directory is deliberately outside the plugin, because plugin directories are
replaced wholesale on every update. It is also not managed by the plugin system:
uninstalling Rock leaves the virtualenv, the catalog and the log behind, and
deleting the directory is the way to reclaim them.

`rock.log` is the first place to look when a command fails for no visible reason;
it holds the full traceback that the command itself did not print.

## When the connection fails

Work through it in this order:

1. **Are the variables set?** The error names the missing ones if not.
2. **Is `ROCK_BASE_URL` right,** including `https://` and no trailing path?
3. **Are you on the network Rock is reachable from?** This is the usual answer.
   Rock instances are commonly not exposed to the open internet.
4. **Does the account still work in a browser?** Passwords expire, accounts get
   locked, permissions get changed.

Report all four with the result of each, and scope the conclusion to what you
checked: "cannot reach it from here" is what these four establish.

## When a write is refused

```
Refusing to run 'person-update': it modifies a person record, and it was not
reached through rock.sh.
```

That means the script was run directly rather than through the entry point. Run
it as `rock.sh query person-update ...`; the entry point is what logs the call
and enables the write.
