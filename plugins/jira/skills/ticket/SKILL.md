---
name: ticket
description: >
  Fetch a Jira ticket and hold it as context for whatever the user asked for.
  Triggers on any message containing a Jira issue key (e.g. ABC-12345),
  whether the ask is to spec it, implement it, review it, or something else
  entirely.
---

# Jira ticket as context

A **context bridge**. The ticket is background for the user's real request, so fetch it and then get on with what they actually asked for.

## Step 1: Extract the issue key and the intent

The key matches `[A-Z]+-\d+`. If the message carries none, ask for one rather than guessing.

Done when you hold a key and have matched the request to one of the branches in Step 5.

## Step 2: Fetch the ticket

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ticket/scripts/fetch_ticket.py" <ISSUE_KEY>
```

Credentials come from the environment, falling back to `~/.claude/passion.env` — the script works from any directory. On a missing variable it exits naming the variable, the file it belongs in, and where to get a token; relay that message as it stands.

It prints the ticket as JSON. Two fields need care:

- `comments` — `{ author, created, updated, body }`, oldest first. Treat them as authoritative over the description: clarifications, scope changes, and acceptance criteria all land here after the fact.
- `attachments` — `{ filename, mime_type, size, is_image, download_url, local_path }`. Images are downloaded to `local_path`, outside any repository. Everything else is listed as metadata only.

## Step 3: Read the images

Read every attachment that has `is_image: true` and a `local_path`, before you act on the ticket — a screenshot or a mockup carries detail that appears nowhere in the text. Where `local_path` is `null` the download failed: give the user the `download_url` and work from the text.

Done when every image attachment has been Read or reported as failed.

## Step 4: Format the context

```
Jira Ticket: <key>
Type: <issue_type>
Status: <status>
Priority: <priority>
Assignee: <assignee>
Labels: <labels joined by comma, or "none">

Summary: <summary>

Description:
<description, or "No description provided">

Comments (<count>):
- <author> (<created>): <body>
- ...
(or "No comments")

Attachments (<count>):
- <filename> (<mime_type>) — <local_path if image, else "not downloaded">
(or "No attachments")
```

An `[image: ...]` marker in the description or a comment body names an entry in `attachments` — pair them up where it matters.

## Step 5: Act on the intent

The skills below live in the `plan` and `dev` plugins, which not every department installs. Confirm a skill is there before you reach for it; where it is missing, name the plugin that carries it and do the work yourself with the ticket in hand.

- **A spec, or an implementation** — `to-spec` and `implement` are user-invoked, so name the one that fits and let the user run it. The context block you just built is what it reads.
- **A review** — invoke `code-review`, with the ticket context as the spec to review against.
- **A specific task** ("for ABC-123 add a logout button to the header") — hold the ticket as background and do the task.
- **Ambiguous** ("jira ABC-123" and nothing else) — show the context block and ask what they want done with it.

When you write the prose deliverable yourself instead of handing off, it is finished only once `/general:to-ste` has run over it in **flavored** mode — a write-up is general prose, not a procedure. Exempt the code blocks, identifiers, log excerpts, and anything quoted from the ticket or its comments.

## Cookbook

<If: the fetch returns 404>
<Then: Jira also returns 404 for a ticket the account cannot see, so ask the user to confirm both the key and their access to that project.>

<If: the description is empty>
<Then: say so, and build the context from the summary and the comments.>
