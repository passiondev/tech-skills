#!/usr/bin/env python3
"""The stand-ins every Jira runtime test is built on.

Not a test module -- `unittest discover` only loads `test*.py`, so this is
imported by name from the files that are.

The fake sits at the curl boundary, which is the only place these scripts touch
the outside world. It records the argv and the stdin of each invocation and
replies from a canned list, so a test can assert three unlike things through one
seam: what was sent, what the caller did with an answer, and what a person is
told when the answer is a failure.

`Reply` is an HTTP answer. `Transport` is curl not coming back with one at all —
a refused connection, a bad certificate, a proxy. The two used to be
indistinguishable downstream, which is the bug these tests exist for.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JIRA_SCRIPTS = ROOT / "plugins" / "jira" / "runtime" / "scripts"

# The credentials the entry points would otherwise read from the developer's own
# ~/.claude/passion.env. Set before the modules load so nothing prompts, and
# named so a test asserting the token never reaches argv has something to look
# for.
os.environ.setdefault("JIRA_BASE_URL", "https://mycompany.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "someone@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "shibboleth-not-in-argv")

if str(JIRA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(JIRA_SCRIPTS))

import fetch_ticket    # noqa: E402
import jira_client     # noqa: E402
import sprint_report   # noqa: E402


class Reply:
    """One HTTP answer: a status, and a body curl writes where it was told to."""

    def __init__(self, status=200, body="", payload=None):
        self.status = status
        self.body = json.dumps(payload) if payload is not None else body


class Transport:
    """curl exiting non-zero, having never got an answer."""

    def __init__(self, exit_code=7, stderr="curl: (7) Failed to connect"):
        self.exit_code = exit_code
        self.stderr = stderr


class Garbage:
    """Whatever curl printed, verbatim -- for the no-status-line case."""

    def __init__(self, stdout="", exit_code=0, stderr=""):
        self.stdout = stdout
        self.exit_code = exit_code
        self.stderr = stderr


class Call:
    """One curl invocation, read back the way a test wants to ask about it."""

    def __init__(self, argv, stdin, timeout):
        self.argv = list(argv)
        self.stdin = stdin or ""
        self.timeout = timeout

    def _after(self, flag):
        return self.argv[self.argv.index(flag) + 1] if flag in self.argv else None

    @property
    def method(self):
        return self._after("-X") or "GET"

    @property
    def url(self):
        # The URL is the only argument that is neither a flag nor a flag's value.
        skip = False
        for i, arg in enumerate(self.argv[1:], 1):
            if skip:
                skip = False
                continue
            if arg.startswith("-"):
                skip = arg in ("-w", "-u", "-H", "-X", "-d", "-o", "--config")
                continue
            return arg
        return None

    @property
    def body(self):
        sent = self._after("-d")
        return json.loads(sent) if sent else None

    @property
    def headers(self):
        return [self.argv[i + 1] for i, a in enumerate(self.argv) if a == "-H"]

    @property
    def out_file(self):
        return self._after("-o")


class FakeCurl:
    """Stands in for `subprocess.run`, one level below JiraClient.

    Replies are consumed in order. Running past the end is a test writing fewer
    replies than the code makes requests, which is worth failing loudly rather
    than answering 200 forever -- a paging loop would spin.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, argv, input=None, capture_output=None, text=None,
                 timeout=None):
        call = Call(argv, input, timeout)
        self.calls.append(call)
        if not self.replies:
            raise AssertionError(
                f"curl called {len(self.calls)} times with no reply left for "
                f"{call.method} {call.url}")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, Transport):
            return _Completed("", reply.stderr, reply.exit_code)
        if isinstance(reply, Garbage):
            return _Completed(reply.stdout, reply.stderr, reply.exit_code)
        if call.out_file:
            # curl writes the body to the file, so stdout carries only the status.
            Path(call.out_file).write_text(reply.body, encoding="utf-8")
            return _Completed(f"\n{reply.status}", "", 0)
        return _Completed(f"{reply.body}\n{reply.status}", "", 0)

    @property
    def urls(self):
        return [c.url for c in self.calls]


class _Completed:
    def __init__(self, stdout, stderr, returncode):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


TOKEN = "shibboleth-not-in-argv"


def client(*replies):
    """A JiraClient whose curl is a fake. Returns the pair, both needed.

    The fake replaces the client's own `_run`, so nothing patches `subprocess`
    for the process -- `test_checks.py` shells out to git in the same run.
    """
    fake = FakeCurl(*replies)
    made = jira_client.JiraClient("https://mycompany.atlassian.net/",
                                  "someone@example.com", TOKEN)
    made._run = fake
    return made, fake
