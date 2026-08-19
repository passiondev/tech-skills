#!/usr/bin/env python3
"""Fetch JIRA ticket details and output structured context for plan generation.

Pulls the ticket's summary/description, all comments, and downloads any image
attachments locally so they can be read into context. Requests go through
jira_client, which uses curl to avoid macOS SSL certificate issues with urllib.

Credentials come from the environment, falling back to ~/.claude/passion.env:
    JIRA_BASE_URL: JIRA instance URL (e.g., https://mycompany.atlassian.net)
    JIRA_EMAIL: JIRA user email
    JIRA_API_TOKEN: JIRA API token

Usage:
    python3 fetch_ticket.py ABC-12345
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jira_client  # noqa: E402

# Attachments are written outside every repository, so a screenshot pulled from a
# ticket can never be committed by accident. See ADR 0001.
DOWNLOAD_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude") / "jira-attachments"

FIELDS = "summary,description,status,priority,labels,issuetype,assignee,comment,attachment"


def fetch_ticket(client, issue_key: str) -> dict:
    try:
        ticket = client.get(f"issue/{issue_key}", params={"fields": FIELDS})
    except jira_client.JiraNotFound:
        # Jira answers 404 for a ticket that is not there and for one this
        # account cannot see, and the reader has to check both.
        raise jira_client.JiraError(
            f"Ticket {issue_key} not found. Confirm the key, and that your "
            "Jira account can see that project.") from None
    if not isinstance(ticket, dict):
        raise jira_client.JiraError(
            f"Jira answered for {issue_key} with no ticket in the body.")
    return ticket


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


def process_attachments(client, attachment_field, issue_key: str) -> list:
    """List all attachments; download image attachments locally for context.

    One image that will not download is not a reason to lose the ticket, so a
    failure is recorded against that attachment and the rest carry on. What
    failed is recorded too: the reader is told to fall back to the URL, and
    "403" and "the file is gone" call for different next steps.
    """
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
            "download_error": None,
        }

        if entry["is_image"] and content_url:
            if not made_dir:
                os.makedirs(download_dir, exist_ok=True)
                made_dir = True
            # Prefix with attachment id to avoid collisions on duplicate filenames.
            att_id = a.get("id")
            safe_name = f"{att_id}_{filename}" if att_id else filename
            dest = os.path.join(download_dir, safe_name)
            try:
                client.download(content_url, dest)
                entry["local_path"] = dest
            except jira_client.JiraError as exc:
                entry["download_error"] = str(exc)
                if os.path.exists(dest):
                    os.remove(dest)

        out.append(entry)

    return out


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_ticket.py <ISSUE_KEY>", file=sys.stderr)
        sys.exit(1)

    issue_key = sys.argv[1].strip().upper()

    with jira_client.api_errors_reported():
        client = jira_client.JiraClient()
        data = fetch_ticket(client, issue_key)

        fields = data.get("fields") or {}
        key = data.get("key", issue_key)
        assignee_field = fields.get("assignee")

        output = {
            "key": key,
            "summary": fields.get("summary", ""),
            "description": extract_description(fields.get("description")),
            # `or {}` rather than a default: Jira sends these fields as null on
            # an unprioritised issue rather than omitting them, so a default
            # only fires for the field that is absent and the read still
            # crashes on the field that is there and empty. sprint_report.py
            # has always guarded this way.
            "status": (fields.get("status") or {}).get("name", "Unknown"),
            "priority": (fields.get("priority") or {}).get("name", "None"),
            "labels": fields.get("labels") or [],
            "issue_type": (fields.get("issuetype") or {}).get("name", "Task"),
            "assignee": assignee_field.get("displayName", "Unassigned") if assignee_field else "Unassigned",
            "comments": extract_comments(fields.get("comment")),
            "attachments": process_attachments(client, fields.get("attachment"), key),
        }

    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
