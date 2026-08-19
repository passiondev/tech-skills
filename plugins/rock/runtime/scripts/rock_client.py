"""Rock RMS REST API client.

Authenticates via cookie-based session (POST /api/Auth/Login).

Rock v17 API limits this module works around: no nested $expand, so workflow
trees are assembled with sequential calls; no contains(), so filters use
substringof(); IsComponent is absent from EntityType, Path from BlockType, and
FriendlyScheduleText from Schedule.

Usage:
  uv run scripts/rock_client.py status    # test connection
"""

import json
import os
import sys
import traceback
from pathlib import Path

import requests
import yaml

import passion_env
from rock_log import get_logger

log = get_logger("rock.client")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_credentials():
    config = load_config()
    base_url, username, password = passion_env.require(
        config["base_url_env"], config["username_env"], config["password_env"]
    )
    if not base_url.startswith("https://"):
        log.error("ROCK_BASE_URL not HTTPS: %s", base_url[:20])
        print(f"Error: ROCK_BASE_URL must use HTTPS (got: {base_url[:20]}...)")
        print("  Credentials must not be transmitted over plain HTTP.")
        sys.exit(1)
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
            print(f"Error: Rock login failed. Check ROCK_USERNAME and ROCK_PASSWORD in {passion_env.ENV_FILE}")
            sys.exit(1)
        log.error("login unexpected status=%d user=%s body=%s",
                   resp.status_code, self._username, resp.text[:200])
        resp.raise_for_status()

    def get(self, endpoint, params=None, timeout=30):
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=timeout)
        self._handle_error(resp, "GET", endpoint, params=params)
        log.info("GET %s ok %dB", endpoint, len(resp.content))
        return resp.json() if resp.content else None

    def post(self, endpoint, data=None, params=None, timeout=30):
        """POST, with or without a JSON body.

        Some Rock routes are convention-based rather than OData, and bind their
        arguments from the query string with no body at all — SetAttributeValue
        is the one this runtime uses. Passing `json=None` sends no body, which
        is what those routes need: a body makes the request match the OData
        route instead, and that 404s.
        """
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.post(url, json=data, params=params, timeout=timeout)
        self._handle_error(resp, "POST", endpoint, params=params, data=data)
        result = None
        if resp.status_code == 201:
            try:
                result = int(resp.text.strip())
            except (ValueError, TypeError):
                pass
        if result is None:
            result = resp.json() if resp.content else None
        log.info("POST %s ok id=%s", endpoint, result)
        return result

    def patch(self, endpoint, data, timeout=30):
        """Change only the fields in `data`, leaving every other column alone.

        This is the verb for any partial update. See `put` for why.
        """
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.patch(url, json=data, timeout=timeout)
        self._handle_error(resp, "PATCH", endpoint, data=data)
        log.info("PATCH %s ok", endpoint)
        return True

    def put(self, endpoint, data, timeout=30):
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
        """
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.put(url, json=data, timeout=timeout)
        self._handle_error(resp, "PUT", endpoint, data=data)
        log.info("PUT %s ok", endpoint)
        return True

    def delete(self, endpoint, timeout=30):
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        resp = self.session.delete(url, timeout=timeout)
        self._handle_error(resp, "DELETE", endpoint)
        log.info("DELETE %s ok", endpoint)
        return True

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
            raise ValueError(f"Not found (404): {detail}")

        log.error(
            "%s %s status=%d params=%s data=%s\n  response: %s\n  traceback:\n%s",
            method, endpoint, status,
            json.dumps(params)[:200] if params else None,
            json.dumps(data)[:200] if data else None,
            detail_str[:500],
            "".join(traceback.format_stack()),
        )

        if status == 401:
            print(f"Error: session expired or auth failed. Check credentials in {passion_env.ENV_FILE}")
            sys.exit(1)
        elif status == 403:
            print("Error: access denied (403). Account may lack permissions for this endpoint.")
            sys.exit(1)
        elif status == 429:
            print("Error: rate limited by Rock API. Try again later.")
            sys.exit(1)
        else:
            raise RuntimeError(f"Rock API HTTP {status}: {detail_str}")


def odata_str(value):
    """Escape a string for safe use in OData $filter expressions."""
    return value.replace("'", "''")


def main():
    client = RockClient()
    try:
        campuses = client.get("Campuses", params={"$top": 1})
        print(f"Connected to Rock RMS at {client.base_url}")
        if campuses and len(campuses) > 0:
            print(f"  Campus: {campuses[0].get('Name', 'unknown')}")
    except Exception as e:
        print(f"Failed to connect to Rock RMS at {client.base_url}")
        print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
