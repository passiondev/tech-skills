"""Rock RMS REST API client.

Authenticates via cookie-based session (POST /api/Auth/Login).

Rock v17 API limits this module works around: no nested $expand, so workflow
trees are assembled with sequential calls; no contains(), so filters use
substringof(); IsComponent is absent from EntityType, Path from BlockType, and
FriendlyScheduleText from Schedule.

Every method here either returns or raises. None of them ends the process: a
failed request is a `RockError`, and the one place that decides a raise stops
the program is `api_errors_reported`, which entry points wrap their body in.
That split is what lets a caller mid-plan report the three entities it already
created before it exits.

Usage:
  uv run scripts/rock_client.py status    # test connection
"""

import json
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

import requests
import yaml

import passion_env
from rock_log import get_logger

log = get_logger("rock.client")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

BASE_URL_ENV = "ROCK_BASE_URL"
USERNAME_ENV = "ROCK_USERNAME"
PASSWORD_ENV = "ROCK_PASSWORD"


class RockError(RuntimeError):
    """Anything that stops this runtime talking to Rock.

    Carries the operator-facing wording with it, so the message a person sees
    for a 403 is written once and not once per command.
    """

    def operator_message(self):
        return str(self)


class RockConfigError(RockError):
    """The credentials or the base URL are missing or unusable."""


class RockApiError(RockError):
    """Rock answered with a status the caller has to deal with."""

    def __init__(self, status, method, endpoint, detail):
        self.status = status
        self.method = method
        self.endpoint = endpoint
        self.detail = detail
        super().__init__(f"Rock API HTTP {status} on {method} {endpoint}: {detail}")

    def operator_message(self):
        return f"Error: {self}"


class RockNotFound(RockApiError):
    """The row is not there.

    Lookup ladders raise past this one on purpose: "not an integer" and "no such
    row" are both "try the next strategy", and a ladder catches both.
    """

    def operator_message(self):
        return f"Error: not found (404): {self.endpoint}"


class RockAuthError(RockApiError):
    """401 or 403. Either the credentials are wrong or the account cannot."""

    def operator_message(self):
        if self.status == 401:
            return ("Error: Rock login failed or the session expired. "
                    f"Check {USERNAME_ENV} and {PASSWORD_ENV} in {passion_env.ENV_FILE}")
        return (f"Error: access denied (403) on {self.method} {self.endpoint}. "
                "The account may lack permission for this endpoint.")


class RockRateLimited(RockApiError):
    """429."""

    def operator_message(self):
        return "Error: rate limited by the Rock API. Try again later."


_STATUS_ERRORS = {404: RockNotFound, 401: RockAuthError, 403: RockAuthError,
                  429: RockRateLimited}


@contextmanager
def api_errors_reported():
    """Print one operator message for a Rock failure, then exit 1.

    This is the only place in the runtime that turns a Rock error into a dead
    process. Entry points wrap their body in it; library code does not, so a
    handler is free to catch a 403 and finish reporting what it managed to do.
    """
    try:
        yield
    except RockError as exc:
        print(exc.operator_message())
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Error: could not reach Rock. {exc}")
        sys.exit(1)


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_credentials():
    base_url, username, password = passion_env.require(
        BASE_URL_ENV, USERNAME_ENV, PASSWORD_ENV
    )
    if not base_url.startswith("https://"):
        log.error("%s not HTTPS: %s", BASE_URL_ENV, base_url[:20])
        raise RockConfigError(
            f"Error: {BASE_URL_ENV} must use HTTPS (got: {base_url[:20]}...)\n"
            "  Credentials must not be transmitted over plain HTTP."
        )
    return base_url.rstrip("/"), username, password


class RockClient:
    def __init__(self, base_url=None, username=None, password=None):
        if base_url and username and password:
            self.base_url = base_url.rstrip("/")
            self._username = username
            self._password = password
        else:
            self.base_url, self._username, self._password = get_credentials()
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._login()

    def _login(self):
        url = f"{self.base_url}/api/Auth/Login"
        resp = self.session.post(url, json={
            "Username": self._username,
            "Password": self._password,
        }, timeout=30)
        if resp.status_code == 204:
            log.info("login ok user=%s", self._username)
            return
        if resp.status_code == 401:
            log.error("login failed user=%s status=401", self._username)
            raise RockAuthError(401, "POST", "Auth/Login", "login rejected")
        log.error("login unexpected status=%d user=%s body=%s",
                   resp.status_code, self._username, resp.text[:200])
        raise RockApiError(resp.status_code, "POST", "Auth/Login", resp.text[:200])

    def _request(self, method, endpoint, params=None, data=None, timeout=30):
        """Send one request. Every verb below goes through here.

        `json=data` with `data` None sends no body at all, which some Rock
        routes require: SetAttributeValue binds from the query string, and a
        body makes the request match the OData route instead and 404.
        """
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.request(method, url, json=data, params=params,
                                    timeout=timeout)
        self._handle_error(resp, method, endpoint, params=params, data=data)
        log.info("%s %s ok %dB", method, endpoint, len(resp.content))
        return resp

    def get(self, endpoint, params=None, timeout=30):
        resp = self._request("GET", endpoint, params=params, timeout=timeout)
        return resp.json() if resp.content else None

    def post(self, endpoint, data=None, params=None, timeout=30):
        """POST, with or without a JSON body.

        Returns the created id where Rock answers 201 with one, otherwise the
        parsed body.
        """
        resp = self._request("POST", endpoint, params=params, data=data,
                             timeout=timeout)
        result = None
        if resp.status_code == 201:
            try:
                result = int(resp.text.strip())
            except (ValueError, TypeError):
                pass
        if result is None:
            result = resp.json() if resp.content else None
        log.info("POST %s id=%s", endpoint, result)
        return result

    def patch(self, endpoint, data, timeout=30):
        """Change only the fields in `data`, leaving every other column alone.

        This is the verb for any partial update. See `put` for why.
        """
        self._request("PATCH", endpoint, data=data, timeout=timeout)
        return True

    def put(self, endpoint, data, *, full_replace, timeout=30):
        """Replace the whole entity. Almost never what you want — use `patch`.

        Rock's PUT is not a merge. `ApiController<T>.Put` calls
        `Service.SetValues(value, target)`, which is
        `Entry(target).CurrentValues.SetValues(source)` — Entity Framework
        copies every mapped column from the object you posted, including the
        ones you left out. So a partial body:

          * nulls every field you omitted, and 400s instead where one of them
            is `[Required]`;
          * wipes CreatedDateTime and CreatedByPersonAliasId, because
            RockPreSave only fills those on insert and never restores them;
          * replaces the row's Guid with a fresh random one, because
            `Entity<T>` initialises its backing field with `Guid.NewGuid()`
            and an absent Guid is indistinguishable from a new entity's.

        A caller that means it must send the entity back whole — every field it
        read, including Id, Guid, and the Created* pair.

        `full_replace` is keyword-only and has no default, so the difference
        between this and `patch` is visible at the call site rather than left to
        a reviewer, a docstring, or a CI pattern over the source text.
        """
        if not full_replace:
            raise ValueError(
                "put() replaces every column in the row, nulling the ones you "
                "omit. Pass full_replace=True and send the entity back whole, "
                "or call patch() to change only the fields you supply."
            )
        self._request("PUT", endpoint, data=data, timeout=timeout)
        return True

    def delete(self, endpoint, timeout=30):
        self._request("DELETE", endpoint, timeout=timeout)
        return True

    def set_attribute_value(self, entity, entity_id, key, value, timeout=30):
        """Set one attribute value on one entity.

        Rock routes this by convention rather than through OData and binds both
        arguments from the query string:

          POST /api/{Entity}/AttributeValue/{id}?attributeKey=K&attributeValue=V

        with no body. Neither parameter is optional — omit attributeKey and the
        request stops matching the route at all. A body is worse than ignored:
        it makes the request match the OData route, which is where the 404s that
        went unnoticed for the life of this plugin came from.

        An unrecognised key is a 400 and nothing is written, so the raise
        propagates. The shape this replaced swallowed both.
        """
        return self.post(f"{entity}/AttributeValue/{entity_id}", params={
            "attributeKey": key,
            "attributeValue": "" if value is None else str(value),
        }, timeout=timeout)

    def _handle_error(self, resp, method="?", endpoint="?", params=None, data=None):
        if resp.ok:
            return
        status = resp.status_code
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text

        detail_str = json.dumps(detail, indent=2) if isinstance(detail, (dict, list)) else str(detail)

        # 404s are expected in lookup helpers -- log at debug, not error
        if status == 404:
            log.debug("%s %s status=404", method, endpoint)
            raise RockNotFound(404, method, endpoint, detail)

        log.error(
            "%s %s status=%d params=%s data=%s\n  response: %s\n  traceback:\n%s",
            method, endpoint, status,
            json.dumps(params)[:200] if params else None,
            json.dumps(data)[:200] if data else None,
            detail_str[:500],
            "".join(traceback.format_stack()),
        )
        raise _STATUS_ERRORS.get(status, RockApiError)(
            status, method, endpoint, detail_str)


def odata_str(value):
    """Escape a string for safe use in OData $filter expressions."""
    return value.replace("'", "''")


def main():
    with api_errors_reported():
        client = RockClient()
        campuses = client.get("Campuses", params={"$top": 1})
        print(f"Connected to Rock RMS at {client.base_url}")
        if campuses:
            print(f"  Campus: {campuses[0].get('Name', 'unknown')}")


if __name__ == "__main__":
    main()
