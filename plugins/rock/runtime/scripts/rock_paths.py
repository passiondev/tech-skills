"""Where the Rock runtime keeps its state.

Everything mutable — the catalog cache, the log, screenshots, the virtualenv —
lives under one fixed directory in the user's home. It cannot live beside the
scripts: ``${CLAUDE_PLUGIN_ROOT}`` is replaced wholesale on every plugin update.
``${CLAUDE_PLUGIN_DATA}`` survives an update, and the runtime lived outside it
originally because two Rock plugins had two of them and needed one virtualenv
and one catalog between them. There is one plugin now (ADR 0023), and the path
stays where it is: it is where every machine's virtualenv, catalog and log
already sit. See ADRs 0016 and 0023.

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
