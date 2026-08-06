#!/usr/bin/env bash
# Add the write half of the Rock runtime to the shared runtime directory.
#
# rock-build depends on rock and reuses its virtualenv and its shared modules
# rather than installing a second copy — see ADR 0013. All this does is drop
# rock_build.py alongside them and make sure the runtime exists.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCK_HOME="${ROCK_HOME:-$HOME/.claude/passion-rock}"
STAMP="$ROCK_HOME/.installed-build"

# The read runtime has to be in place first: rock_build.py imports rock_client,
# rock_log, and rock_paths from it. rock is a hard dependency of rock-build, so
# it is installed — it may simply not have been bootstrapped yet.
if [[ ! -f "$ROCK_HOME/pyproject.toml" ]]; then
  SIBLING="$(dirname "$(dirname "$SRC")")/rock/runtime/bootstrap.sh"
  if [[ -x "$SIBLING" ]]; then
    "$SIBLING"
  else
    cat >&2 <<MSG
The Rock runtime is not installed yet, and I could not find the rock plugin's
bootstrap to run it.

Run any Rock read command first — "rock status" will do it — then try again.
MSG
    exit 1
  fi
fi

NEW="$(shasum -a 256 "$SRC/scripts/rock_build.py" | awk '{print $1}')"
if [[ -f "$STAMP" ]] && [[ "$NEW" == "$(cat "$STAMP")" ]] && [[ -f "$ROCK_HOME/scripts/rock_build.py" ]]; then
  exit 0
fi

cp "$SRC/scripts/rock_build.py" "$ROCK_HOME/scripts/"
printf '%s' "$NEW" > "$STAMP"
echo "Rock build runtime ready." >&2
