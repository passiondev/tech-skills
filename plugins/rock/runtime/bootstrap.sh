#!/usr/bin/env bash
# Install the Rock runtime into ~/.claude/passion-rock (or $ROCK_HOME).
#
# Idempotent and cheap to re-run: it compares a manifest of what it last
# installed against what the plugin now ships, and does nothing when they
# match. ${CLAUDE_PLUGIN_ROOT} is replaced on every plugin update, so the
# runtime cannot live there. See ADRs 0003 and 0016.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCK_HOME="${ROCK_HOME:-$HOME/.claude/passion-rock}"
STAMP="$ROCK_HOME/.installed"

if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<'MSG'
Rock needs `uv` to manage its Python dependencies, and it is not installed.

  macOS / Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh
  Windows:        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  Homebrew:       brew install uv

Then run this again. Nothing else is required — uv brings its own Python.
MSG
  exit 1
fi

# Manifest = every shipped file plus its checksum. Any edit anywhere changes it.
manifest() {
  find "$SRC" -type f \( -name '*.py' -o -name '*.toml' -o -name '*.lock' -o -name '*.yaml' \) \
    -not -path '*/.venv/*' | sort | xargs shasum -a 256 | sed "s|$SRC/||"
}

mkdir -p "$ROCK_HOME"

# rock-build used to install rock_build.py separately and stamp it here. One
# plugin ships the whole runtime now (ADR 0023), so the stamp is dead weight
# that would outlive every upgrade if nothing removed it.
rm -f "$ROCK_HOME/.installed-build"

# Asking for the browser is sticky, and it has to be part of the stamp. The
# manifest covers shipped files only, so ROCK_WITH_BROWSER=1 was invisible to
# the comparison below and the documented opt-in no-opped on every machine that
# had already run a Rock command — which is all of them, because the first Rock
# command is what installs the runtime. Sticky also means a later plain run
# re-syncs with the group instead of uninstalling Playwright behind you.
BROWSER_MARK="$ROCK_HOME/.browser"
[[ "${ROCK_WITH_BROWSER:-}" == "1" ]] && : > "$BROWSER_MARK"

NEW="$(manifest)"
[[ -f "$BROWSER_MARK" ]] && NEW="$NEW"$'\n'"group:browser"

if [[ -f "$STAMP" ]] && [[ "$NEW" == "$(cat "$STAMP")" ]]; then
  exit 0
fi

echo "Installing the Rock runtime into $ROCK_HOME ..." >&2

mkdir -p "$ROCK_HOME/scripts"
cp "$SRC"/pyproject.toml "$SRC"/uv.lock "$ROCK_HOME/"
cp "$SRC"/scripts/*.py "$ROCK_HOME/scripts/"

SYNC_ARGS=(--frozen)
[[ -f "$BROWSER_MARK" ]] && SYNC_ARGS+=(--group browser)

( cd "$ROCK_HOME" && uv sync "${SYNC_ARGS[@]}" )

# uv installs the Playwright package. The browser binary it drives is a
# separate download, and nothing else here performs it.
if [[ -f "$BROWSER_MARK" ]]; then
  echo "Downloading Chromium (~150 MB, once) ..." >&2
  ( cd "$ROCK_HOME" && uv run --frozen playwright install chromium )
fi

printf '%s' "$NEW" > "$STAMP"
echo "Rock runtime ready." >&2
