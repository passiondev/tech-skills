"""Where the Rock runtime keeps its state.

Everything mutable — the catalog cache, the log, screenshots, the virtualenv —
lives under one fixed directory in the user's home. It cannot live beside the
scripts: ``${CLAUDE_PLUGIN_ROOT}`` is replaced wholesale on every plugin update.
It cannot live in ``${CLAUDE_PLUGIN_DATA}`` either, because ``rock`` and
``rock-build`` are two plugins with two data directories that must share one
virtualenv and one catalog. See ADR 0016.

Override with ROCK_HOME when you need a second instance's state kept apart.
"""

import os
from pathlib import Path

HOME = Path(os.environ.get("ROCK_HOME") or Path.home() / ".claude" / "passion-rock")

SCRIPTS = HOME / "scripts"
VENV = HOME / ".venv"
CATALOG = HOME / "catalog.json"
LOG = HOME / "rock.log"
SCREENSHOTS = HOME / "screenshots"
SNAPSHOTS = HOME / "snapshots"


def ensure() -> Path:
    """Create the runtime directory if it is missing, and return it."""
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME
