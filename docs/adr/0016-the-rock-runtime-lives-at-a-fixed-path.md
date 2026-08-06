# The Rock runtime lives at a fixed path, and the read/write boundary is enforced in code

Both Rock plugins install their Python into `~/.claude/passion-rock`, overridable with `ROCK_HOME`. One virtualenv, one catalog, one log, one screenshots directory, shared by `rock` and `rock-build`. And `rock_query.py` refuses its four write subcommands unless `ROCK_ALLOW_WRITES=1`, which only `rock-build` sets.

Two corrections to earlier decisions, both found while porting the code.

## The path

[0003](0003-rock-bundles-its-runtime.md) said the runtime installs into `${CLAUDE_PLUGIN_DATA}` because that directory survives plugin updates, which `${CLAUDE_PLUGIN_ROOT}` does not. Both halves of that are true. The problem is that `${CLAUDE_PLUGIN_DATA}` is `~/.claude/plugins/data/{plugin-id}/` — one directory per plugin. [0013](0013-rock-splits-into-read-and-write.md) then split Rock into two plugins that must share one virtualenv, and noticed the tension in passing without resolving it.

A shared runtime needs a path neither plugin owns. `~/.claude/passion-rock` is that path: it survives updates for the same reason `${CLAUDE_PLUGIN_DATA}` does — it is outside the plugin directory — and `rock-build` can install `rock_build.py` next to the modules it imports. `rock_paths.py` is the single place any of this is spelled, so the six runtime modules resolve their state through it rather than each computing a path from `__file__`.

`rock-build`'s bootstrap needs the read runtime present before it can add to it. If `$ROCK_HOME/pyproject.toml` is missing it runs `../rock/runtime/bootstrap.sh` — a sibling, because both plugins are installed from the same marketplace under one `plugins/` directory — and if that is not there either, it says so and exits rather than half-installing.

## The guard

[0013](0013-rock-splits-into-read-and-write.md) says: "The read-only guarantee ... holds because `rock_query.py` issues no writes." That is false. `rock_query.py` has four subcommands that write to Rock:

| subcommand | call |
| --- | --- |
| `person-create` | `POST People` |
| `person-update` | `PUT People/{id}` |
| `block-set` | `POST Blocks/{id}/AttributeValues`, `PUT Blocks/AttributeValue/{id}` |
| `exception-clear` | `DELETE ExceptionLogs/{id}` |

So the boundary [0013](0013-rock-splits-into-read-and-write.md) was drawn to create did not exist. A service and support person installing `rock` to look things up would have had a person-record editor on disk, reachable by asking for it.

The four commands stay where they are — they are query-shaped, they share the query script's argument handling, and moving them would be a bigger change than the boundary needs. Instead `main()` refuses them unless `ROCK_ALLOW_WRITES=1` is set, which happens only in `rock-build`'s skills. The refusal names the command, what it would have changed, and which plugin to ask for.

## Considered options

- **Keep the runtime in `${CLAUDE_PLUGIN_DATA}` and duplicate it per plugin.** Two virtualenvs, two `uv sync` runs, two catalogs drifting apart, and `rock_build.py` unable to import `rock_client` without a third copy. Rejected: the duplication [0013](0013-rock-splits-into-read-and-write.md) set out to avoid.
- **`rock` symlinks its data directory to `rock-build`'s, or vice versa.** Keeps the documented mechanism. Rejected because it depends on install order and on which plugin was updated last, and a broken symlink after an uninstall is a worse failure than a missing directory.
- **Move the four write commands into `rock_build.py`.** The honest fix — the boundary would then be structural, and no guard would be needed. Rejected for now because it is a real refactor of a 66 KB file we vendored rather than wrote, and the guard buys the same safety today. Worth doing when that script is next opened for other reasons.
- **Document the four commands as off-limits and leave the code alone.** What [0013](0013-rock-splits-into-read-and-write.md) effectively did. Rejected: a boundary that a skill instruction can talk its way past is not a boundary, and the whole reason for two plugins was to stop the safety rule living inside instructions.

## Consequences

`~/.claude/passion-rock` is not managed by the plugin system. Uninstalling both Rock plugins leaves the virtualenv, the catalog and the log behind. That is a few hundred megabytes of stale Python nobody will think to delete — `rock`'s setup skill should say where it is so the answer exists somewhere.

The guard is an environment variable, so anything that can set the environment can pass it. It stops accidents and casual asking, not a determined person, and [0013](0013-rock-splits-into-read-and-write.md) already notes that Rock's own credentials are one account with one permission set. The real limit on what someone can change in Rock is that account's permissions, not this.

`ROCK_ALLOW_WRITES` has to be set by every `rock-build` skill that calls a guarded command, and nothing fails loudly if a new skill forgets — the command refuses, which reads as a bug rather than an omission. The four command names are listed in one dict at the top of `rock_query.py`; a fifth write command added to that script without being added to the dict is unguarded and silent. CI should compare that dict against the script's actual write calls.

Two bootstraps run per Rock session in the worst case, one chaining into the other. Both are checksum-gated no-ops after the first run — 0.05s — so the cost is a subprocess, not an install.
