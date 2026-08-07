#!/usr/bin/env bash
# The one way to run anything in the Rock runtime.
#
#   rock.sh query workflows --limit 20
#   rock.sh catalog status
#   rock.sh browser screenshot /volunteers
#
# Bootstraps on first use and after any plugin update; a no-op (~0.05s)
# otherwise.
#
# Reads only. The write subcommands refuse unless ROCK_ALLOW_WRITES is set,
# which only rock-build sets — the refusal comes before any network call, so
# a write reaches Rock from this path never. Note the guard sits behind
# argument parsing, so an incomplete write command reports its missing
# arguments rather than the refusal; neither one writes. See ADR 0016.
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
