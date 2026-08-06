#!/usr/bin/env bash
# The one way to run anything that changes Rock.
#
#   rock.sh build /tmp/plan.json
#   rock.sh query audit "Volunteer Signup"
#   rock.sh query block-set 4821 EnableDebug false
#
# Identical to the rock plugin's entry point except that it sets
# ROCK_ALLOW_WRITES, which unlocks the four write subcommands of
# rock_query.py. See ADR 0016.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCK_HOME="${ROCK_HOME:-$HOME/.claude/passion-rock}"

"$HERE/bootstrap.sh"

TOOL="${1:-}"
case "$TOOL" in
  build|query|catalog|browser) shift ;;
  *) echo "usage: rock.sh <build|query|catalog|browser> [args...]" >&2; exit 64 ;;
esac

export ROCK_ALLOW_WRITES=1
exec uv run --project "$ROCK_HOME" python "$ROCK_HOME/scripts/rock_$TOOL.py" "$@"
