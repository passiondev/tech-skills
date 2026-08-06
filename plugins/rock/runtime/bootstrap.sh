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
NEW="$(manifest)"

if [[ -f "$STAMP" ]] && [[ "$NEW" == "$(cat "$STAMP")" ]]; then
  exit 0
fi

echo "Installing the Rock runtime into $ROCK_HOME ..." >&2

mkdir -p "$ROCK_HOME/scripts"
cp "$SRC"/pyproject.toml "$SRC"/uv.lock "$SRC"/config.yaml "$ROCK_HOME/"
cp "$SRC"/scripts/*.py "$ROCK_HOME/scripts/"

SYNC_ARGS=(--frozen)
[[ "${ROCK_WITH_BROWSER:-}" == "1" ]] && SYNC_ARGS+=(--group browser)

( cd "$ROCK_HOME" && uv sync "${SYNC_ARGS[@]}" )

printf '%s' "$NEW" > "$STAMP"
echo "Rock runtime ready." >&2
