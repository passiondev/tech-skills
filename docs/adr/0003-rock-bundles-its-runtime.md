# The rock plugin carries its own runtime, minus the browser

The `rock` capability plugin ships the Python that talks to Rock — six modules, `pyproject.toml`, `uv.lock`, `config.yaml` — inside the plugin. Its dependencies install once into `${CLAUDE_PLUGIN_DATA}`, and every file it writes at runtime goes there too. Playwright becomes an optional dependency group that nobody gets unless they ask for it. The only prerequisite is `uv`. *[0016](0016-the-rock-runtime-lives-at-a-fixed-path.md) moves the install target to `~/.claude/passion-rock`, since `${CLAUDE_PLUGIN_DATA}` is per-plugin and two plugins share this runtime.*

Rock is the one skill whose value is unreachable without executable code, and the audience includes departments that will never clone a repo. So the alternative — a thin plugin that shells into a local `rock-tools` checkout — would have reintroduced exactly the gatekeeping [0001](0001-public-marketplace-repo.md) removed: access to a private repo, plus `just`, `jq`, and `setup.sh`, before anything works.

Bundling looked expensive until the dependency graph was actually read. `playwright` is imported by one module, `rock_browser.py`, which nothing else imports; authentication is plain `requests` against `POST /api/Auth/Login`. Forty-three of the forty-seven operations therefore need only `requests`, `pyyaml`, and `python-dotenv` — pure-Python wheels totalling a few hundred kilobytes. Only screenshots and page verification need a browser, and they are verification aids, not the capability. Making Playwright optional turns a ~150 MB Chromium download for everyone into a fast install for everyone and a slow one for the few who want pixels.

## Consequences

`rock_catalog.py` resolves its cache relative to the scripts directory. That has to change: `${CLAUDE_PLUGIN_ROOT}` is replaced on every plugin update and cleaned up weeks later, so a catalog written beside the scripts would silently vanish. The catalog, the log, and any screenshots must resolve somewhere that survives updates — `rock_paths.py`, per [0016](0016-the-rock-runtime-lives-at-a-fixed-path.md).

`python-dotenv` turned out to be unnecessary: [0005](0005-credentials-live-in-one-passion-env.md) reads `passion.env` in about twenty lines of `passion_env.py`, so the shipped runtime is `requests` and `pyyaml` only.

The plugin needs a bootstrap step to install its dependencies on first use and again whenever an update changes the manifest. It also needs to fail legibly when `uv` is absent, since that is now the single point of failure for the whole plugin.

`just` and `jq` stop being prerequisites. The `rock-*` recipes are one-line wrappers, so the skills call the scripts directly.
