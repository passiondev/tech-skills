#!/usr/bin/env python3
"""Fetch JIRA ticket details and output structured context for plan generation.

Pulls the ticket's summary/description, all comments, and downloads any image
attachments locally so they can be read into context. Uses curl for HTTP
requests to avoid macOS SSL certificate issues with urllib.

Credentials come from the environment, falling back to ~/.claude/passion.env:
    JIRA_BASE_URL: JIRA instance URL (e.g., https://mycompany.atlassian.net)
    JIRA_EMAIL: JIRA user email
    JIRA_API_TOKEN: JIRA API token

Usage:
    python3 fetch_ticket.py ABC-12345
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import passion_env  # noqa: E402

# Attachments are written outside every repository, so a screenshot pulled from a
# ticket can never be committed by accident. See ADR 0001.
DOWNLOAD_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude") / "jira-attachments"


def _auth():
    # require() is idempotent, so this is safe to call per attachment; it also
    # means the download path fails with a named variable rather than a 401.
    return passion_env.require("JIRA_EMAIL", "JIRA_API_TOKEN")


def fetch_ticket(issue_key: str) -> dict:
    base_url, email, token = passion_env.require("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    base_url = base_url.rstrip("/")

    fields = "summary,description,status,priority,labels,issuetype,assignee,comment,attachment"
    url = f"{base_url}/rest/api/3/issue/{issue_key}?fields={fields}"

    result = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-u", f"{email}:{token}", "-H", "Accept: application/json", url],
        capture_output=True, text=True, timeout=30,
    )

    lines = result.stdout.rsplit("\n", 1)
    body = lines[0] if len(lines) > 1 else result.stdout
    status_code = int(lines[1]) if len(lines) > 1 else 0

    if status_code == 404:
        print(f"ERROR: Ticket {issue_key} not found", file=sys.stderr)
        sys.exit(1)
    elif status_code == 401:
        print("ERROR: Authentication failed — check JIRA_EMAIL and JIRA_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    elif status_code == 403:
        print(f"ERROR: Permission denied for ticket {issue_key}", file=sys.stderr)
        sys.exit(1)
    elif status_code < 200 or status_code >= 300:
        print(f"ERROR: JIRA API returned {status_code}", file=sys.stderr)
        sys.exit(1)

    return json.loads(body)


def extract_adf_text(node: dict) -> str:
    """Flatten an ADF node to plain text, leaving markers where media (images) appear."""
    node_type = node.get("type")
    if node_type == "text":
        return node.get("text", "")
    # Inline/block media nodes reference an attachment by id; surface a marker so
    # the reader knows an image sits here and can match it to a download below.
    if node_type in ("media", "mediaInline", "mediaSingle"):
        attrs = node.get("attrs", {})
        ref = attrs.get("alt") or attrs.get("id") or "attachment"
        # mediaSingle wraps a child media node — recurse first, fall back to marker.
        inner = "\n".join(filter(None, (extract_adf_text(c) for c in node.get("content", []))))
        return inner or f"[image: {ref}]"
    parts = []
    for child in node.get("content", []):
        parts.append(extract_adf_text(child))
    return "\n".join(filter(None, parts))


def extract_description(description) -> str:
    if not description:
        return ""
    if isinstance(description, str):
        return description
    if isinstance(description, dict):
        return extract_adf_text(description)
    return ""


def extract_comments(comment_field) -> list:
    if not isinstance(comment_field, dict):
        return []
    out = []
    for c in comment_field.get("comments", []):
        author = (c.get("author") or {}).get("displayName", "Unknown")
        out.append({
            "author": author,
            "created": c.get("created", ""),
            "updated": c.get("updated", ""),
            "body": extract_description(c.get("body")),
        })
    return out


def download_attachment(url: str, dest_path: str) -> bool:
    email, token = _auth()
    result = subprocess.run(
        ["curl", "-s", "-L", "-w", "%{http_code}", "-u", f"{email}:{token}", "-o", dest_path, url],
        capture_output=True, text=True, timeout=60,
    )
    # With -o, the body is written to the file, so stdout is only %{http_code}.
    code = result.stdout.strip()
    return code.isdigit() and 200 <= int(code) < 300


def process_attachments(attachment_field, issue_key: str) -> list:
    """List all attachments; download image attachments locally for context."""
    if not isinstance(attachment_field, list):
        return []

    download_dir = str(DOWNLOAD_ROOT / issue_key)
    out = []
    made_dir = False

    for a in attachment_field:
        mime = a.get("mimeType", "") or ""
        filename = a.get("filename", "attachment")
        content_url = a.get("content", "")
        entry = {
            "filename": filename,
            "mime_type": mime,
            "size": a.get("size"),
            "is_image": mime.startswith("image/"),
            "download_url": content_url,
            "local_path": None,
        }

        if entry["is_image"] and content_url:
            if not made_dir:
                os.makedirs(download_dir, exist_ok=True)
                made_dir = True
            # Prefix with attachment id to avoid collisions on duplicate filenames.
            att_id = a.get("id")
            safe_name = f"{att_id}_{filename}" if att_id else filename
            dest = os.path.join(download_dir, safe_name)
            if download_attachment(content_url, dest):
                entry["local_path"] = dest
            elif os.path.exists(dest):
                os.remove(dest)

        out.append(entry)

    return out


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_ticket.py <ISSUE_KEY>", file=sys.stderr)
        sys.exit(1)

    issue_key = sys.argv[1].strip().upper()
    data = fetch_ticket(issue_key)

    fields = data.get("fields", {})
    key = data.get("key", issue_key)
    summary = fields.get("summary", "")
    description = extract_description(fields.get("description"))
    status = fields.get("status", {}).get("name", "Unknown")
    priority = fields.get("priority", {}).get("name", "None")
    labels = fields.get("labels", [])
    issue_type = fields.get("issuetype", {}).get("name", "Task")
    assignee_field = fields.get("assignee")
    assignee = assignee_field.get("displayName", "Unassigned") if assignee_field else "Unassigned"
    comments = extract_comments(fields.get("comment"))
    attachments = process_attachments(fields.get("attachment"), key)

    output = {
        "key": key,
        "summary": summary,
        "description": description,
        "status": status,
        "priority": priority,
        "labels": labels,
        "issue_type": issue_type,
        "assignee": assignee,
        "comments": comments,
        "attachments": attachments,
    }

    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
