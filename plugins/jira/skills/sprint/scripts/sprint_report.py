#!/usr/bin/env python3
"""Summarise the current sprint for the authenticated Jira user.

The report is written outside every repository unless a destination is given.

Credentials come from the environment, falling back to ~/.claude/passion.env:
    JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
Optional:
    JIRA_PROJECT   default project key when --project is not passed

Usage:
    python3 sprint_report.py --project ABC
    python3 sprint_report.py --project ABC --out ~/reports/sprint.md
    python3 sprint_report.py --project ABC --json
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import passion_env  # noqa: E402

# Jira groups every status into one of three built-in categories: new,
# indeterminate, done. Bucketing on the category rather than on status names
# keeps this script free of any one instance's configured workflow.
SECTIONS = (("In progress", "indeterminate"), ("To do", "new"))


def _call(args: list) -> dict:
    result = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}"] + args,
        capture_output=True, text=True, timeout=60,
    )
    body, _, code = result.stdout.rpartition("\n")
    status = int(code) if code.strip().isdigit() else 0

    if status == 401:
        sys.exit("ERROR: authentication failed — check JIRA_EMAIL and JIRA_API_TOKEN")
    if status < 200 or status >= 300:
        detail = ""
        try:
            detail = "; ".join(json.loads(body).get("errorMessages", []))
        except (ValueError, AttributeError):
            detail = body[:300]
        sys.exit(f"ERROR: Jira returned {status}. {detail}".rstrip())

    return json.loads(body)


def search(base_url: str, email: str, token: str, jql: str) -> list:
    """Every matching issue. The endpoint pages at maxResults and reports more
    with isLast/nextPageToken, so a single call silently drops the tail of a
    busy sprint."""
    issues = []
    token_page = None
    while True:
        page = {"jql": jql,
                "fields": ["summary", "status", "priority", "duedate"],
                "maxResults": 100}
        if token_page:
            page["nextPageToken"] = token_page
        data = _call(["-u", f"{email}:{token}",
                      "-H", "Accept: application/json",
                      "-H", "Content-Type: application/json",
                      "-X", "POST", f"{base_url}/rest/api/3/search/jql",
                      "-d", json.dumps(page)])
        issues += data.get("issues", [])
        token_page = data.get("nextPageToken")
        if data.get("isLast", True) or not token_page:
            return issues


def project_exists(base_url: str, email: str, token: str, project: str) -> bool:
    """The search endpoint answers an unknown project key with an empty result,
    identical to a real project with no open sprint. This tells them apart."""
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "-u", f"{email}:{token}", "-H", "Accept: application/json",
         f"{base_url}/rest/api/3/project/{project}"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip() != "404"


def normalise(issues: list) -> list:
    out = []
    for issue in issues:
        f = issue.get("fields", {})
        out.append({
            "key": issue.get("key", ""),
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", "Unknown"),
            "category": (((f.get("status") or {}).get("statusCategory")) or {}).get("key", "undefined"),
            "priority": (f.get("priority") or {}).get("name", "None"),
            "due": f.get("duedate"),
        })
    return out


def table(rows: list, show_priority: bool = True) -> list:
    head = ["Key", "Summary", "Status"] + (["Priority"] if show_priority else []) + ["Due"]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        cells = [r["key"], r["summary"].replace("|", "\\|"), r["status"]]
        if show_priority:
            cells.append(r["priority"])
        cells.append(r["due"] or "-")
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render(rows: list, project: str, today: str) -> str:
    out = [f"# Sprint report — {project} — {today}", ""]

    # Overdue leads: the skill's Step 2 asks for what needs attention first.
    overdue = [r for r in rows if r["due"] and r["due"] < today and r["category"] != "done"]
    if overdue:
        out += ["## Overdue", ""] + table(overdue, show_priority=False) + [""]

    for title, category in SECTIONS:
        section = [r for r in rows if r["category"] == category]
        if section:
            out += [f"## {title}", ""] + table(section) + [""]

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    out += ["## Summary", ""]
    out += [f"- **{s}**: {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    out += [f"- **Total**: {len(rows)}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=os.environ.get("JIRA_PROJECT", ""),
                    help="Jira project key. Defaults to $JIRA_PROJECT.")
    ap.add_argument("--out", help="Write the report here. Defaults to stdout.")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of markdown.")
    args = ap.parse_args()

    base_url, email, token = passion_env.require("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    project = args.project or os.environ.get("JIRA_PROJECT", "")
    if not project:
        sys.exit("ERROR: no project key. Pass --project ABC or set JIRA_PROJECT in ~/.claude/passion.env")

    base_url = base_url.rstrip("/")
    jql = (f"project = {project} AND assignee = currentUser() "
           "AND sprint in openSprints() ORDER BY status ASC, priority DESC")
    rows = normalise(search(base_url, email, token, jql))

    if not rows and not project_exists(base_url, email, token, project):
        sys.exit(f"ERROR: no project {project} on this Jira site, or your account cannot see it. "
                 "Check the key, or pass --project with the right one.")

    if args.json:
        json.dump({"project": project, "issues": rows}, sys.stdout, indent=2)
        return

    today = dt.date.today().isoformat()
    report = render(rows, project, today)

    if args.out:
        dest = Path(args.out).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(report, encoding="utf-8")
        print(f"Report saved to {dest}")
    else:
        print(report)


if __name__ == "__main__":
    main()
