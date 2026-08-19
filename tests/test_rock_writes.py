#!/usr/bin/env python3
"""Every write the Rock plugins can send, asserted request by request.

These tests exist because of one API detail that is invisible from the call
site: Rock's ``PUT`` is a full-entity replace, not a merge. ``ApiController.Put``
hands the posted object to ``CurrentValues.SetValues``, so Entity Framework
copies *every* mapped column — the ones you omitted included. A partial PUT
therefore nulls the fields you left out, wipes ``CreatedDateTime`` and
``CreatedByPersonAliasId`` (``RockPreSave`` only restores those on insert), and
replaces the row's ``Guid`` with a fresh random one, because ``Entity<T>``
initialises its backing field with ``Guid.NewGuid()``. Where a nulled column is
``[Required]`` the request 400s and the operation is simply dead; where it is
not, the write succeeds and quietly corrupts the row.

Nothing in a code review shows that. What shows it is asserting the method and
the URL, which is all these tests do: no Rock, no network, a recording fake in
place of the client. If a future edit reaches for ``put`` again for a partial
update, a test here fails and names the operation.

Run:  python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ROCK_SCRIPTS = ROOT / "plugins" / "rock" / "runtime" / "scripts"
BUILD_SCRIPTS = ROOT / "plugins" / "rock-build" / "runtime" / "scripts"

# The runtime logs to $ROCK_HOME on import. Keep that out of the developer's
# real runtime directory.
_LOG_HOME = tempfile.mkdtemp(prefix="rock-tests-")
os.environ["ROCK_HOME"] = _LOG_HOME


def _stub(name, **attrs):
    """Register a stand-in module so an import of a third-party package works.

    check.py keeps CI stdlib-only and there is no virtualenv here, so `requests`
    and `yaml` are not installed. Neither is reached: every test builds a client
    with an explicit fake session or bypasses the client entirely.
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


_stub("requests", Session=_session_factory)
_stub("yaml", safe_load=lambda *a, **k: {})

for _p in (str(ROCK_SCRIPTS), str(BUILD_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import rock_build            # noqa: E402
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

    def put(self, endpoint, data, timeout=30):
        self._record("PUT", endpoint, data=data)
        return True

    def delete(self, endpoint, timeout=30):
        self._record("DELETE", endpoint)
        return True

    # -- assertions --------------------------------------------------------
    @property
    def writes(self):
        return [c for c in self.calls if c["method"] != "GET"]

    def only_write(self):
        writes = self.writes
        assert len(writes) == 1, f"expected exactly one write, got {writes}"
        return writes[0]


CATALOG = {
    "action_components": [
        {"name": "Set Attribute Value", "class_name": "Rock.Workflow.Action.SetAttributeValue",
         "entity_type_id": 501},
    ],
    "field_types": [{"name": "Text", "id": 1}],
    "block_types": [{"name": "Group Detail", "id": 77}],
    "layouts": [{"name": "Full Width", "id": 5, "site_id": 1}],
}


class WriteTestCase(unittest.TestCase):
    def assertNoPut(self, client):
        puts = [c for c in client.calls if c["method"] == "PUT"]
        self.assertEqual(
            puts, [],
            "PUT replaces the whole entity in Rock — a partial update must use PATCH")

    def assertSucceeded(self, result):
        self.assertTrue(result.success, f"operation reported failure: {result.failed}")


# ─────────────────────────────────────────────────────────────────────────────
# RockClient — the two verbs the partial-update fix needs
# ─────────────────────────────────────────────────────────────────────────────

class TestClientVerbs(unittest.TestCase):
    def client(self):
        c = rock_client.RockClient(base_url="https://example.com",
                                   username="svc", password="x")
        return c, _SESSIONS[-1]

    def test_patch_sends_a_patch_with_the_supplied_body(self):
        c, session = self.client()
        session.sent.clear()
        c.patch("WorkflowTypes/12", {"Name": "Renamed"})
        sent = session.sent[-1]
        self.assertEqual(sent["method"], "PATCH")
        self.assertEqual(sent["url"], "https://example.com/api/WorkflowTypes/12")
        self.assertEqual(sent["json"], {"Name": "Renamed"})

    def test_post_forwards_query_parameters(self):
        c, session = self.client()
        session.sent.clear()
        c.post("Blocks/AttributeValue/9", params={"attributeKey": "K", "attributeValue": "V"})
        sent = session.sent[-1]
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["params"], {"attributeKey": "K", "attributeValue": "V"})

    def test_post_without_data_sends_no_body(self):
        """Rock's SetAttributeValue route binds from the query string only.

        A JSON body on that route is not merely ignored — the route it matches
        is the OData one, which 404s."""
        c, session = self.client()
        session.sent.clear()
        c.post("Blocks/AttributeValue/9", params={"attributeKey": "K", "attributeValue": "V"})
        self.assertIsNone(session.sent[-1]["json"])

    def test_post_still_reads_the_created_id_out_of_a_201(self):
        c, session = self.client()
        session.next_response = _FakeResponse(201, text="4821")
        self.assertEqual(c.post("Groups", {"Name": "Team"}), 4821)
        session.next_response = None

    def test_put_still_exists_for_deliberate_full_replacement(self):
        c, session = self.client()
        session.sent.clear()
        c.put("Groups/3", {"Name": "Team", "GroupTypeId": 1})
        self.assertEqual(session.sent[-1]["method"], "PUT")


# ─────────────────────────────────────────────────────────────────────────────
# Attribute values — the route that never worked
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributeValues(WriteTestCase):
    def test_uses_the_convention_route_with_query_string_parameters(self):
        client = FakeClient()
        rock_build.set_attribute_values(client, "Blocks", 4821, {"EnableDebug": "false"})
        call = client.only_write()
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["endpoint"], "Blocks/AttributeValue/4821")
        self.assertEqual(call["params"],
                         {"attributeKey": "EnableDebug", "attributeValue": "false"})
        self.assertIsNone(call["data"], "the key and value go in the query string, not a body")

    def test_values_are_stringified_and_none_becomes_empty(self):
        client = FakeClient()
        rock_build.set_attribute_values(client, "Blocks", 1, {"A": 7, "B": True, "C": None})
        values = [c["params"]["attributeValue"] for c in client.writes]
        self.assertEqual(values, ["7", "True", ""])

    def test_a_rejected_key_is_raised_not_printed(self):
        """The old code caught this and printed `Warning:`, and the entity was
        still reported as created — so a whole workflow could come back green
        with none of its actions configured."""
        client = FakeClient(fail_on={"Blocks/AttributeValue/1"})
        with self.assertRaises(RuntimeError):
            rock_build.set_attribute_values(client, "Blocks", 1, {"Nope": "x"})

    def test_a_rejected_key_fails_the_build(self):
        client = FakeClient(fail_on={"Blocks/AttributeValue/1"})
        result = rock_build.BuildResult()
        ok = rock_build.apply_settings(result, client, "Blocks", 1, "a block", {"Nope": "x"})
        self.assertFalse(ok)
        self.assertFalse(result.success)


# ─────────────────────────────────────────────────────────────────────────────
# The partial updates that were PUTs
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialUpdatesUsePatch(WriteTestCase):
    def test_update_workflow(self):
        client = FakeClient()
        result = rock_build.update_workflow(
            {"modification": {"workflow_type_id": 12, "updates": {"description": "New"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "WorkflowTypes/12",
                          "params": None, "data": {"Description": "New"}})

    def test_update_activity(self):
        client = FakeClient()
        result = rock_build.update_activity(
            {"modification": {"activity_type_id": 34, "updates": {"order": 2}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write()["endpoint"], "WorkflowActivityTypes/34")
        self.assertEqual(client.only_write()["data"], {"Order": 2})

    def test_update_action(self):
        client = FakeClient()
        result = rock_build.update_action(
            {"modification": {"action_type_id": 56, "updates": {"name": "Renamed"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write()["method"], "PATCH")
        self.assertEqual(client.only_write()["endpoint"], "WorkflowActionTypes/56")

    def test_reorder_actions(self):
        client = FakeClient()
        result = rock_build.reorder_actions(
            {"modification": {"action_order": [7, 8]}}, client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual([(c["method"], c["endpoint"], c["data"]) for c in client.writes],
                         [("PATCH", "WorkflowActionTypes/7", {"Order": 0}),
                          ("PATCH", "WorkflowActionTypes/8", {"Order": 1})])

    def test_move_action(self):
        client = FakeClient()
        result = rock_build.move_action(
            {"modification": {"action_type_id": 7, "target_activity_type_id": 34}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        call = client.only_write()
        self.assertEqual(call["method"], "PATCH")
        self.assertEqual(call["data"], {"ActivityTypeId": 34, "Order": 0})

    def test_checkin_area_schedule_link(self):
        client = FakeClient()
        result = rock_build.create_checkin_area(
            {"checkin_area": {"name": "Nursery", "group_type_id": 15, "schedules": [99]}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        schedule_call = client.writes[-1]
        self.assertEqual(schedule_call["method"], "PATCH")
        self.assertEqual(schedule_call["data"], {"ScheduleId": 99})


# ─────────────────────────────────────────────────────────────────────────────
# Groups — the operations that were never written
# ─────────────────────────────────────────────────────────────────────────────

class TestGroupOperations(WriteTestCase):
    def test_create_group_posts_the_group(self):
        client = FakeClient()
        result = rock_build.create_group(
            {"group": {"name": "Guest Services", "group_type_id": 25,
                       "parent_group_id": 8, "campus_id": 1,
                       "description": "Front door team"}},
            client, CATALOG)
        self.assertSucceeded(result)
        call = client.only_write()
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["endpoint"], "Groups")
        self.assertEqual(call["data"], {
            "Name": "Guest Services", "GroupTypeId": 25, "IsActive": True,
            "IsPublic": True, "IsSecurityRole": False, "Order": 0,
            "ParentGroupId": 8, "CampusId": 1, "Description": "Front door team"})

    def test_create_group_resolves_the_group_type_by_name(self):
        client = FakeClient(responses={"GroupTypes": [{"Id": 25}]})
        result = rock_build.create_group(
            {"group": {"name": "Guest Services", "group_type": "Serving Team"}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["data"]["GroupTypeId"], 25)

    def test_create_group_fails_loudly_when_the_type_cannot_be_resolved(self):
        client = FakeClient()
        result = rock_build.create_group(
            {"group": {"name": "Guest Services", "group_type": "No Such Type"}},
            client, CATALOG)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [], "nothing should be created")

    def test_create_group_applies_settings(self):
        client = FakeClient()
        result = rock_build.create_group(
            {"group": {"name": "Team", "group_type_id": 25,
                       "settings": {"AllowGuests": "True"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.writes[-1]["endpoint"], "Groups/AttributeValue/1001")

    def test_update_group_patches(self):
        client = FakeClient()
        result = rock_build.update_group(
            {"modification": {"group_id": 31, "updates": {"name": "Renamed",
                                                          "is_active": False}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "Groups/31", "params": None,
                          "data": {"Name": "Renamed", "IsActive": False}})

    def test_add_group_member(self):
        client = FakeClient()
        result = rock_build.add_group_member(
            {"modification": {"group_id": 31, "person_id": 42, "group_role_id": 3}},
            client, CATALOG)
        self.assertSucceeded(result)
        call = client.only_write()
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["endpoint"], "GroupMembers")
        self.assertEqual(call["data"], {"GroupId": 31, "PersonId": 42,
                                        "GroupRoleId": 3, "GroupMemberStatus": 1,
                                        "IsNotified": False, "IsArchived": False})

    def test_add_group_member_resolves_the_role_within_the_groups_type(self):
        """A role name is only unique inside its group type, so resolving it
        needs the group's GroupTypeId first."""
        client = FakeClient(responses={
            "Groups/31": {"Id": 31, "GroupTypeId": 25},
            "GroupTypeRoles": [{"Id": 3}],
        })
        result = rock_build.add_group_member(
            {"modification": {"group_id": 31, "person_id": 42, "role": "Leader"}},
            client, CATALOG)
        self.assertSucceeded(result)
        role_lookup = [c for c in client.calls if c["endpoint"] == "GroupTypeRoles"]
        self.assertTrue(role_lookup, "should look up GroupTypeRoles")
        self.assertIn("GroupTypeId eq 25", role_lookup[0]["params"]["$filter"])
        self.assertEqual(client.only_write()["data"]["GroupRoleId"], 3)

    def test_add_group_member_maps_a_status_name(self):
        client = FakeClient()
        for name, expected in (("active", 1), ("inactive", 0), ("pending", 2)):
            client.calls.clear()
            result = rock_build.add_group_member(
                {"modification": {"group_id": 1, "person_id": 2, "group_role_id": 3,
                                  "status": name}}, client, CATALOG)
            self.assertSucceeded(result)
            self.assertEqual(client.only_write()["data"]["GroupMemberStatus"], expected,
                             f"status {name!r}")

    def test_add_group_member_rejects_an_unknown_status(self):
        client = FakeClient()
        result = rock_build.add_group_member(
            {"modification": {"group_id": 1, "person_id": 2, "group_role_id": 3,
                              "status": "probationary"}}, client, CATALOG)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])

    def test_update_group_member_patches(self):
        client = FakeClient()
        result = rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"status": "inactive",
                                                                 "note": "moved away"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "GroupMembers/88", "params": None,
                          "data": {"GroupMemberStatus": 0, "Note": "moved away"}})

    def test_remove_group_member_deletes(self):
        client = FakeClient()
        result = rock_build.remove_group_member(
            {"modification": {"group_member_id": 88}}, client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write(),
                         {"method": "DELETE", "endpoint": "GroupMembers/88",
                          "params": None, "data": None})

    def test_create_group_sync(self):
        client = FakeClient(responses={
            "Groups/31": {"Id": 31, "GroupTypeId": 25},
            "GroupTypeRoles": [{"Id": 3}],
            "DataViews": [{"Id": 71}],
        })
        result = rock_build.create_group_sync(
            {"modification": {"group_id": 31, "role": "Member",
                              "data_view": "Active Adults",
                              "add_user_accounts": True,
                              "schedule_interval_minutes": 720}},
            client, CATALOG)
        self.assertSucceeded(result)
        call = client.only_write()
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["endpoint"], "GroupSyncs")
        self.assertEqual(call["data"], {
            "GroupId": 31, "GroupTypeRoleId": 3, "SyncDataViewId": 71,
            "AddUserAccountsDuringSync": True, "ScheduleIntervalMinutes": 720})

    def test_create_group_sync_needs_a_data_view(self):
        client = FakeClient(responses={"Groups/31": {"Id": 31, "GroupTypeId": 25},
                                       "GroupTypeRoles": [{"Id": 3}]})
        result = rock_build.create_group_sync(
            {"modification": {"group_id": 31, "role": "Member",
                              "data_view": "No Such View"}}, client, CATALOG)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])


# ─────────────────────────────────────────────────────────────────────────────
# The generic escape hatch
# ─────────────────────────────────────────────────────────────────────────────

class TestApiRequest(WriteTestCase):
    def test_sends_the_request_verbatim(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "POST", "endpoint": "GroupMemberRequirements",
                         "body": {"GroupMemberId": 88, "GroupRequirementId": 4}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write(),
                         {"method": "POST", "endpoint": "GroupMemberRequirements",
                          "params": None,
                          "data": {"GroupMemberId": 88, "GroupRequirementId": 4}})

    def test_forwards_query_parameters(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "POST", "endpoint": "Groups/AttributeValue/31",
                         "params": {"attributeKey": "K", "attributeValue": "V"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["params"],
                         {"attributeKey": "K", "attributeValue": "V"})

    def test_patch_is_allowed_without_ceremony(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PATCH", "endpoint": "Groups/31",
                         "body": {"Name": "Renamed"}}}, client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "PATCH")

    def test_put_is_refused_without_an_acknowledgement(self):
        """The whole point of the fix is that PUT replaces the entity. The
        escape hatch must not be a back door to the bug."""
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31",
                         "body": {"Name": "Renamed"}}}, client, CATALOG)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])
        self.assertIn("full_replace", result.failed["error"])

    def test_put_is_allowed_with_an_acknowledgement(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31", "full_replace": True,
                         "body": {"Id": 31, "Name": "Renamed", "GroupTypeId": 25,
                                  "Guid": "0000", "CreatedDateTime": "2020-01-01"}}},
            client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "PUT")

    def test_a_delete_needs_no_body(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "DELETE", "endpoint": "GroupSyncs/12"}}, client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "DELETE")

    def test_an_unknown_method_is_refused(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "TRACE", "endpoint": "Groups/31"}}, client, CATALOG)
        self.assertFalse(result.success)
        self.assertEqual(client.calls, [])

    def test_an_absolute_url_is_refused(self):
        client = FakeClient()
        for endpoint in ("https://example.org/api/Groups",
                         "../../etc/passwd", "Groups/../../x"):
            result = rock_build.api_request(
                {"request": {"method": "POST", "endpoint": endpoint, "body": {}}},
                client, CATALOG)
            self.assertFalse(result.success, endpoint)
        self.assertEqual(client.calls, [])

    def test_a_missing_endpoint_is_refused(self):
        client = FakeClient()
        result = rock_build.api_request({"request": {"method": "POST"}}, client, CATALOG)
        self.assertFalse(result.success)


class TestWritePermission(unittest.TestCase):
    """rock-build's entry point sets ROCK_ALLOW_WRITES; nothing else does."""

    def setUp(self):
        self._saved = os.environ.get("ROCK_ALLOW_WRITES")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ROCK_ALLOW_WRITES", None)
        else:
            os.environ["ROCK_ALLOW_WRITES"] = self._saved

    def test_refused_when_the_variable_is_absent(self):
        os.environ.pop("ROCK_ALLOW_WRITES", None)
        with self.assertRaises(SystemExit) as caught:
            rock_build.require_writes_enabled("create_group")
        self.assertEqual(caught.exception.code, 2)

    def test_allowed_when_the_variable_is_set(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"
        rock_build.require_writes_enabled("create_group")

    def test_the_guard_runs_before_any_operation_does(self):
        """One dispatch point, so one guard covers every operation — including
        ones added later."""
        import inspect
        src = inspect.getsource(rock_build.main)
        self.assertIn("require_writes_enabled(", src)
        self.assertLess(src.index("require_writes_enabled("), src.index("handler(plan"),
                        "the guard must run before the operation does")

    def test_every_registered_operation_goes_through_that_dispatch(self):
        import inspect
        src = inspect.getsource(rock_build.main)
        self.assertEqual(src.count("handler(plan"), 1)
        self.assertIn("api_request", rock_build.OPERATIONS)
        self.assertIn("create_group", rock_build.OPERATIONS)


# ─────────────────────────────────────────────────────────────────────────────
# rock_query's four guarded writes
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryWrites(WriteTestCase):
    def test_person_update_patches(self):
        client = FakeClient(responses={"People/7": {"Id": 7, "FirstName": "A",
                                                     "LastName": "B"}})
        rock_query.cmd_person_update(
            SimpleNamespace(id="7", fields=["email=someone@example.com"]), client)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "People/7", "params": None,
                          "data": {"Email": "someone@example.com"}})

    def test_block_set_uses_the_convention_route(self):
        client = FakeClient(responses={"Blocks/4821": {"Id": 4821}})
        rock_query.cmd_block_set(
            SimpleNamespace(id="4821", key="EnableDebug", value="false"), client)
        call = client.only_write()
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["endpoint"], "Blocks/AttributeValue/4821")
        self.assertEqual(call["params"],
                         {"attributeKey": "EnableDebug", "attributeValue": "false"})

    def test_person_create_still_posts(self):
        client = FakeClient()
        rock_query.cmd_person_create(
            SimpleNamespace(first="A", last="B", email=None, connection_status=None,
                            record_status=None, campus=None), client)
        self.assertEqual(client.only_write()["method"], "POST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
