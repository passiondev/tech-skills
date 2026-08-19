"""Credential loading for Passion skills.

Real environment variables win. Anything not already set is filled in from
``~/.claude/passion.env``, a plain ``KEY=value`` file that lives outside every
repository so it cannot be committed by accident. See ADR 0005.
"""

import os
import sys
from pathlib import Path

ENV_FILE = Path.home() / ".claude" / "passion.env"


def load() -> None:
    """Fill unset variables from ~/.claude/passion.env. Never overrides the environment."""
    if not ENV_FILE.is_file():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


HINTS = {
    "JIRA_API_TOKEN": "Create one at https://id.atlassian.com/manage/api-tokens",
    "JIRA_BASE_URL": "Your Atlassian site URL, e.g. https://yoursite.atlassian.net",
    "JIRA_EMAIL": "The email address you sign in to Jira with",
    "JIRA_PROJECT": "Default Jira project key, e.g. ABC. Optional — pass --project instead.",
    "ROCK_BASE_URL": "Your Rock instance URL. Must be https.",
    "ROCK_USERNAME": "Your Rock login. Needs admin access.",
    "ROCK_PASSWORD": "Your Rock password.",
}


def require(*names: str) -> list:
    """Return the named variables, or exit with a message naming what is missing."""
    load()
    values = [os.environ.get(n, "").strip() for n in names]
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        lines = [
            f"ERROR: missing {', '.join(missing)}.",
            f"Set them in {ENV_FILE} (one KEY=value per line) or export them in your environment.",
        ]
        lines += [f"  {n} — {HINTS[n]}" for n in missing if n in HINTS]
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)
    return values
