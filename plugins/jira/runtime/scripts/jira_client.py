"""Every request this plugin makes to Jira.

Four call sites each rolled their own curl, and each one knew a little of this
and none of it all: how curl is asked to report a status code, which line of
stdout the body is on, which statuses matter, and what to tell the person when
one comes back. Two of them split the status off with different string methods,
two of them spelled out the same wording for a 401, one handled 403 and the
other did not, and all four read a curl that never ran as status 0 — reported
to the operator as "Jira returned 0."

Every method here either returns or raises. None of them ends the process: a
failed request is a `JiraError`, and the one place that decides a raise stops
the program is `api_errors_reported`, which entry points wrap their body in.
That split is what lets `process_attachments` lose one image and still return
the ticket, and `project_exists` treat a 404 as an answer rather than a fault.
This mirrors `rock_client.py`, which settled the same shape for Rock.

Credentials come from the environment, falling back to ~/.claude/passion.env
(ADR 0005):
    JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
"""

import json
import subprocess
import sys
from contextlib import contextmanager
from urllib.parse import urlencode

import passion_env

BASE_URL_ENV = "JIRA_BASE_URL"
EMAIL_ENV = "JIRA_EMAIL"
TOKEN_ENV = "JIRA_API_TOKEN"

# Every path below hangs off the one Jira REST version this plugin speaks.
API = "rest/api/3"


class JiraError(RuntimeError):
    """Anything that stops this runtime talking to Jira.

    Carries the operator-facing wording with it, so the message a person sees
    for a 401 is written once and not once per script.
    """

    def operator_message(self):
        return f"ERROR: {self}"


class JiraUnreachable(JiraError):
    """curl did not come back with an answer at all.

    A refused connection, a DNS failure, a proxy, an expired certificate, a
    timeout. Told apart from an HTTP status on purpose: the two scripts here
    used to fold this case into "status 0" and report it as a number Jira had
    supposedly returned, which sends the reader looking at Jira for a fault
    that is on this side of the wire.
    """


class JiraApiError(JiraError):
    """Jira answered with a status the caller has to deal with."""

    def __init__(self, status, method, endpoint, detail):
        self.status = status
        self.method = method
        self.endpoint = endpoint
        self.detail = detail
        super().__init__(f"Jira returned {status} on {method} {endpoint}"
                         + (f". {detail}" if detail else ""))


class JiraNotFound(JiraApiError):
    """404, which Jira also answers for a row the account cannot see.

    Callers catch this one and say what was not found in their own words, since
    "no such ticket" and "no such project" are different sentences and only the
    caller knows which it asked for.
    """


class JiraAuthError(JiraApiError):
    """401 or 403. Either the credentials are wrong or the account cannot."""

    def operator_message(self):
        if self.status == 401:
            return (f"ERROR: authentication failed. Check {EMAIL_ENV} and "
                    f"{TOKEN_ENV} in {passion_env.ENV_FILE}")
        return (f"ERROR: access denied (403) on {self.method} {self.endpoint}. "
                "The account may lack permission for this project.")


_STATUS_ERRORS = {404: JiraNotFound, 401: JiraAuthError, 403: JiraAuthError}


@contextmanager
def api_errors_reported():
    """Print one operator message for a Jira failure, then exit 1.

    This is the only place in the runtime that turns a Jira error into a dead
    process. Entry points wrap their body in it; library code does not, so a
    handler is free to catch a 404 and carry on.

    Messages go to stderr because `fetch_ticket.py` writes the ticket to stdout
    as JSON, and a caller parsing that stream must not find prose in it.
    """
    try:
        yield
    except JiraError as exc:
        print(exc.operator_message(), file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired as exc:
        print(f"ERROR: Jira did not answer within {exc.timeout:g}s.",
              file=sys.stderr)
        sys.exit(1)


def _config_line(email, token):
    """Credentials as a curl config file, for curl to read on stdin.

    `-u email:token` puts the API token in the process arguments, where every
    local user reads it out of `ps` for as long as the request runs. All four
    call sites did that. A config file on stdin is the same authentication with
    nothing on the command line, and curl needs no flag beyond `--config -`.
    """
    def quote(value):
        return value.replace("\\", "\\\\").replace('"', '\\"')

    return f'user = "{quote(email)}:{quote(token)}"\n'


class JiraClient:
    """One authenticated Jira site.

    Built once per run and passed to whatever needs it, so the three
    credentials stop travelling together as three arguments through every
    function that makes a request.
    """

    def __init__(self, base_url=None, email=None, token=None):
        if not (base_url and email and token):
            base_url, email, token = passion_env.require(
                BASE_URL_ENV, EMAIL_ENV, TOKEN_ENV)
        self.base_url = base_url.rstrip("/")
        self._email = email
        self._token = token
        # Bound to the instance rather than called through the module, so a test
        # can hand this client a stand-in for curl without patching `subprocess`
        # for the whole process. curl is the only outside world this module has,
        # so it is the only seam worth opening.
        self._run = subprocess.run

    def _curl(self, method, endpoint, args, timeout):
        """Send one request and return the body and the status.

        `-w "\\n%{http_code}"` appends the status as a final line, so the body
        is everything before the last newline. `-S` keeps curl's own diagnostic
        on stderr even under `-s`, which is what `JiraUnreachable` reports.
        """
        result = self._run(
            ["curl", "-s", "-S", "-w", "\n%{http_code}", "--config", "-",
             "-H", "Accept: application/json"] + args,
            input=_config_line(self._email, self._token),
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise JiraUnreachable(
                f"could not reach Jira for {method} {endpoint} "
                f"(curl exit {result.returncode}). "
                f"{result.stderr.strip()[:200]}".rstrip())
        body, _, code = result.stdout.rpartition("\n")
        if not code.strip().isdigit():
            raise JiraUnreachable(
                f"curl reported no status for {method} {endpoint}. "
                f"{result.stderr.strip()[:200]}".rstrip())
        return body, int(code)

    def _request(self, method, endpoint, args, timeout):
        """One request, parsed, with a raise for anything outside the 2xx range."""
        body, status = self._curl(method, endpoint, args, timeout)
        if status < 200 or status >= 300:
            raise _STATUS_ERRORS.get(status, JiraApiError)(
                status, method, endpoint, _detail(body))
        try:
            return json.loads(body) if body.strip() else None
        except ValueError as exc:
            raise JiraError(f"Jira answered {method} {endpoint} with "
                            f"something that is not JSON: {exc}") from exc

    def get(self, endpoint, params=None, timeout=30):
        """GET one Jira resource. `endpoint` is a path under rest/api/3."""
        url = f"{self.base_url}/{API}/{endpoint.lstrip('/')}"
        if params:
            url += "?" + urlencode(params)
        return self._request("GET", endpoint, [url], timeout)

    def post(self, endpoint, body, timeout=60):
        """POST a JSON body to one Jira resource."""
        return self._request("POST", endpoint, [
            "-H", "Content-Type: application/json", "-X", "POST",
            f"{self.base_url}/{API}/{endpoint.lstrip('/')}",
            "-d", json.dumps(body),
        ], timeout)

    def download(self, url, dest, timeout=60):
        """Fetch an attachment to `dest`, following redirects.

        The URL is absolute and comes from the ticket rather than being built
        here, because Jira serves attachment content from its own path.

        With `-o` the body lands in the file, so the status line is all of
        stdout. A failure raises rather than returning false: the caller wants
        the reason, and the shape this replaced discarded it.
        """
        body, status = self._curl("GET", url, ["-L", "-o", str(dest), url],
                                  timeout)
        if status < 200 or status >= 300:
            raise _STATUS_ERRORS.get(status, JiraApiError)(
                status, "GET", url, _detail(body))
        return True


def _detail(body):
    """What Jira said about a failure, in one line.

    Jira reports most faults as `errorMessages`, and a few as an `errors` map
    keyed by field. Anything else is served as HTML — a proxy's error page, a
    login redirect — so that falls back to a prefix of the raw body, which is
    enough to recognise.
    """
    try:
        parsed = json.loads(body)
    except ValueError:
        return " ".join(body.split())[:300]
    if not isinstance(parsed, dict):
        return " ".join(body.split())[:300]
    said = list(parsed.get("errorMessages") or [])
    said += [f"{k}: {v}" for k, v in (parsed.get("errors") or {}).items()]
    return "; ".join(said) if said else " ".join(body.split())[:300]
