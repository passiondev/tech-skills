#!/usr/bin/env bash
# The one way to run anything in the Rock runtime.
#
#   rock.sh query workflows --limit 20
#   rock.sh catalog status
#   rock.sh browser screenshot /volunteers
#
# Bootstraps on first use and after any plugin update; a no-op (~0.05s)
# otherwise. Runs read commands only — `rock.sh query person-create` is
# refused. See ADR 0016.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCK_HOME="${ROCK_HOME:-$HOME/.claude/passion-rock}"

"$HERE/bootstrap.sh"

TOOL="${1:-}"
case "$TOOL" in
  query|catalog|browser) shift ;;
  *) echo "usage: rock.sh <query|catalog|browser> [args...]" >&2; exit 64 ;;
esac

exec uv run --project "$ROCK_HOME" python "$ROCK_HOME/scripts/rock_$TOOL.py" "$@"
