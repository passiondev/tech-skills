#!/usr/bin/env python3
"""The stand-ins every Rock runtime test is built on.

Not a test module -- `unittest discover` only loads `test*.py`, so this is
imported by name from the files that are.

There are two levels of fake here and the distinction matters. `_FakeSession`
sits under `RockClient` and records the raw HTTP call, which is what a test of
the client itself needs: the method, the URL, whether a body went at all.
`FakeClient` sits above it and records the client call, which is what a test of
an operation needs. A test that asserts a URL uses the first; a test that
asserts what an operation did uses the second.
"""

import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ROCK_SCRIPTS = ROOT / "plugins" / "rock" / "runtime" / "scripts"

# The runtime logs to $ROCK_HOME on import. Keep that out of the developer's
# real runtime directory.
_LOG_HOME = tempfile.mkdtemp(prefix="rock-tests-")
os.environ["ROCK_HOME"] = _LOG_HOME


def _stub(name, **attrs):
    """Register a stand-in module so an import of a third-party package works.

    check.py keeps CI stdlib-only and there is no virtualenv here, so `requests`
    is not installed. It is never reached either: every test builds a client with
    an explicit fake session, or bypasses the client entirely.
    """
    if name in sys.modules:
        return sys.modules[name]
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.reason = ""

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    @property
    def content(self):
        return self.text.encode()

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError(f"HTTP {self.status_code}")


class _FakeSession:
    """Records the raw HTTP call RockClient makes, one level below the client."""

    def __init__(self):
        self.headers = {}
        self.sent = []
        self.next_response = None

    def _record(self, method, url, json=None, params=None, timeout=None):
        self.sent.append({"method": method, "url": url, "json": json,
                          "params": params, "timeout": timeout})
        if url.endswith("/api/Auth/Login"):
            return _FakeResponse(204)
        return self.next_response or _FakeResponse(200, text="")

    def get(self, url, **kw):
        return self._record("GET", url, **kw)

    def post(self, url, **kw):
        return self._record("POST", url, **kw)

    def put(self, url, **kw):
        return self._record("PUT", url, **kw)

    def patch(self, url, **kw):
        return self._record("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self._record("DELETE", url, **kw)

    def request(self, method, url, **kw):
        return self._record(method, url, **kw)


_SESSIONS = []


def _session_factory():
    s = _FakeSession()
    _SESSIONS.append(s)
    return s


_stub("requests", Session=_session_factory, RequestException=OSError)

if str(ROCK_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ROCK_SCRIPTS))

import rock_build            # noqa: E402
import rock_paths           # noqa: E402
import rock_client           # noqa: E402
import rock_query            # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# A recording stand-in for RockClient, one level above the HTTP session.
# ─────────────────────────────────────────────────────────────────────────────

class FakeClient:
    """Records calls instead of making them; replies from a canned table.

    ``responses`` maps an endpoint to what GET should return. ``post`` hands
    back an incrementing id, which is what Rock's 201 body is.
    """

    def __init__(self, responses=None, fail_on=None):
        self.calls = []
        self.responses = responses or {}
        self.fail_on = fail_on or set()
        self._next_id = 1000

    # -- recording ---------------------------------------------------------
    def _record(self, method, endpoint, params=None, data=None):
        self.calls.append({"method": method, "endpoint": endpoint,
                           "params": params, "data": data})
        if (method, endpoint) in self.fail_on or endpoint in self.fail_on:
            raise RuntimeError(f"Rock API HTTP 400: refused {method} {endpoint}")

    def get(self, endpoint, params=None, timeout=30):
        self._record("GET", endpoint, params=params)
        for key, value in self.responses.items():
            if endpoint == key or endpoint.startswith(key.rstrip("*")) and key.endswith("*"):
                return value
        return None

    def post(self, endpoint, data=None, params=None, timeout=30):
        self._record("POST", endpoint, params=params, data=data)
        self._next_id += 1
        return self._next_id

    def patch(self, endpoint, data, timeout=30):
        self._record("PATCH", endpoint, data=data)
        return True

    def put(self, endpoint, data, *, full_replace, timeout=30):
        if not full_replace:
            raise ValueError("put() replaces every column; pass full_replace=True")
        self._record("PUT", endpoint, data=data)
        return True

    def delete(self, endpoint, timeout=30):
        self._record("DELETE", endpoint)
        return True

    def set_attribute_value(self, entity, entity_id, key, value, timeout=30):
        return self.post(f"{entity}/AttributeValue/{entity_id}", params={
            "attributeKey": key,
            "attributeValue": "" if value is None else str(value),
        })

    # -- assertions --------------------------------------------------------
    @property
    def writes(self):
        return [c for c in self.calls if c["method"] != "GET"]

    def only_write(self):
        writes = self.writes
        assert len(writes) == 1, f"expected exactly one write, got {writes}"
        return writes[0]
