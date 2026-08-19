#!/usr/bin/env bash
# The one way to run anything in the Rock runtime.
#
#   rock.sh query workflows --limit 20
#   rock.sh query audit "Volunteer Signup"
#   rock.sh build /tmp/plan.json
#   rock.sh catalog status
#   rock.sh browser screenshot /volunteers
#
# Bootstraps on first use and after any plugin update; a no-op (~0.05s)
# otherwise.
#
# Sets ROCK_ALLOW_WRITES, which every write path in the runtime requires. The
# scripts are copied to $ROCK_HOME and can be run from there directly; the
# guard is what makes that path read-only, so a write that skips this script
# does not reach Rock. See ADR 0023.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCK_HOME="${ROCK_HOME:-$HOME/.claude/passion-rock}"

"$HERE/bootstrap.sh"

TOOL="${1:-}"
case "$TOOL" in
  query|build|catalog|browser) shift ;;
  *) echo "usage: rock.sh <query|build|catalog|browser> [args...]" >&2; exit 64 ;;
esac

export ROCK_ALLOW_WRITES=1
exec uv run --project "$ROCK_HOME" python "$ROCK_HOME/scripts/rock_$TOOL.py" "$@"
