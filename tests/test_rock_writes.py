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

import ast
import inspect
import io
import os
import textwrap
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from rock_harness import (FakeClient, _FakeResponse, _SESSIONS, rock_build,
                          rock_client, rock_paths, rock_query)


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
        self.assertTrue(result.success, f"operation reported failure: {result.failures}")


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
        c.put("Groups/3", {"Name": "Team", "GroupTypeId": 1}, full_replace=True)
        self.assertEqual(session.sent[-1]["method"], "PUT")

    def test_put_refuses_a_caller_that_did_not_say_full_replace(self):
        """The rule used to live only in a CI regex keyed to one function name.

        Renaming the file or the function silently unguarded it. Now the
        signature carries it, so the difference between a merge and a
        whole-entity replace is visible where the call is written."""
        c, session = self.client()
        session.sent.clear()
        with self.assertRaises(ValueError):
            c.put("Groups/3", {"Name": "Team"}, full_replace=False)
        self.assertEqual(session.sent, [], "nothing may leave the process")

    def test_put_cannot_be_called_positionally_like_patch(self):
        c, _ = self.client()
        with self.assertRaises(TypeError):
            c.put("Groups/3", {"Name": "Team"})

    def test_set_attribute_value_uses_the_convention_route(self):
        c, session = self.client()
        session.sent.clear()
        c.set_attribute_value("Blocks", 9, "EnableDebug", False)
        sent = session.sent[-1]
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["url"], "https://example.com/api/Blocks/AttributeValue/9")
        self.assertEqual(sent["params"],
                         {"attributeKey": "EnableDebug", "attributeValue": "False"})
        self.assertIsNone(sent["json"], "a body makes this match the OData route")


class TestClientErrorsAreRaisedNotExited(unittest.TestCase):
    """The client used to call sys.exit on 401, 403 and 429.

    A plan that created three entities and then hit a 403 died inside the
    client, so nothing reported the three. Every verb now raises and one context
    manager at the entry point decides that a raise ends the process."""

    def client(self):
        c = rock_client.RockClient(base_url="https://example.com",
                                   username="svc", password="x")
        return c, _SESSIONS[-1]

    def _raises_on(self, status, expected):
        c, session = self.client()
        session.next_response = _FakeResponse(status, text="nope")
        try:
            with self.assertRaises(expected) as caught:
                c.get("Groups/1")
        finally:
            session.next_response = None
        return caught.exception

    def test_403_raises_an_auth_error(self):
        exc = self._raises_on(403, rock_client.RockAuthError)
        self.assertEqual(exc.status, 403)
        self.assertIn("access denied", exc.operator_message())

    def test_401_raises_an_auth_error_naming_the_env_file(self):
        exc = self._raises_on(401, rock_client.RockAuthError)
        self.assertIn("ROCK_PASSWORD", exc.operator_message())

    def test_429_raises_a_rate_limit_error(self):
        exc = self._raises_on(429, rock_client.RockRateLimited)
        self.assertIn("rate limited", exc.operator_message())

    def test_404_raises_not_found_which_a_lookup_ladder_catches(self):
        exc = self._raises_on(404, rock_client.RockNotFound)
        self.assertIsInstance(exc, rock_client.RockApiError)

    def test_500_raises_the_generic_api_error(self):
        exc = self._raises_on(500, rock_client.RockApiError)
        self.assertEqual(exc.status, 500)

    def test_every_error_is_a_rock_error(self):
        for cls in (rock_client.RockConfigError, rock_client.RockApiError,
                    rock_client.RockNotFound, rock_client.RockAuthError,
                    rock_client.RockRateLimited):
            self.assertTrue(issubclass(cls, rock_client.RockError), cls.__name__)


class TestOneExitPolicy(unittest.TestCase):
    def test_the_context_manager_prints_the_message_and_exits_one(self):
        with self.assertRaises(SystemExit) as caught:
            with rock_client.api_errors_reported():
                raise rock_client.RockAuthError(403, "PATCH", "Groups/1", "no")
        self.assertEqual(caught.exception.code, 1)

    def test_it_lets_anything_that_is_not_a_rock_error_through(self):
        with self.assertRaises(KeyError):
            with rock_client.api_errors_reported():
                raise KeyError("workflow")


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
        """The step stops the plan by raising, so a caller cannot miss it.

        This used to be a False the seven callers were each trusted to check."""
        client = FakeClient(fail_on={"Blocks/AttributeValue/1"})
        result = rock_build.BuildResult()
        with self.assertRaises(rock_build.StepFailed):
            rock_build.apply_settings(result, client, "Blocks", 1, "a block",
                                      {"Nope": "x"})
        self.assertFalse(result.success)
        self.assertEqual(result.failures[0]["type"], "Settings")


# ─────────────────────────────────────────────────────────────────────────────
# The partial updates that were PUTs
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialUpdatesUsePatch(WriteTestCase):
    def test_update_workflow(self):
        client = FakeClient()
        result = rock_build.update_workflow(
            {"modification": {"workflow_type_id": 12, "updates": {"description": "New"}}},
            client)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "WorkflowTypes/12",
                          "params": None, "data": {"Description": "New"}})

    def test_update_activity(self):
        client = FakeClient()
        result = rock_build.update_activity(
            {"modification": {"activity_type_id": 34, "updates": {"order": 2}}},
            client)
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
            {"modification": {"action_order": [7, 8]}}, client)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual([(c["method"], c["endpoint"], c["data"]) for c in client.writes],
                         [("PATCH", "WorkflowActionTypes/7", {"Order": 0}),
                          ("PATCH", "WorkflowActionTypes/8", {"Order": 1})])

    def test_move_action(self):
        client = FakeClient()
        result = rock_build.move_action(
            {"modification": {"action_type_id": 7, "target_activity_type_id": 34}},
            client)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        call = client.only_write()
        self.assertEqual(call["method"], "PATCH")
        self.assertEqual(call["data"], {"ActivityTypeId": 34, "Order": 0})

    def test_checkin_area_schedule_link(self):
        client = FakeClient()
        result = rock_build.create_checkin_area(
            {"checkin_area": {"name": "Nursery", "group_type_id": 15, "schedules": [99]}},
            client)
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
            client)
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
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["data"]["GroupTypeId"], 25)

    def test_create_group_fails_loudly_when_the_type_cannot_be_resolved(self):
        client = FakeClient()
        result = rock_build.create_group(
            {"group": {"name": "Guest Services", "group_type": "No Such Type"}},
            client)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [], "nothing should be created")

    def test_create_group_applies_settings(self):
        client = FakeClient()
        result = rock_build.create_group(
            {"group": {"name": "Team", "group_type_id": 25,
                       "settings": {"AllowGuests": "True"}}},
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.writes[-1]["endpoint"], "Groups/AttributeValue/1001")

    def test_update_group_patches(self):
        client = FakeClient()
        result = rock_build.update_group(
            {"modification": {"group_id": 31, "updates": {"name": "Renamed",
                                                          "is_active": False}}},
            client)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "Groups/31", "params": None,
                          "data": {"Name": "Renamed", "IsActive": False}})

    def test_add_group_member(self):
        client = FakeClient()
        result = rock_build.add_group_member(
            {"modification": {"group_id": 31, "person_id": 42, "group_role_id": 3}},
            client)
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
            client)
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
                                  "status": name}}, client)
            self.assertSucceeded(result)
            self.assertEqual(client.only_write()["data"]["GroupMemberStatus"], expected,
                             f"status {name!r}")

    def test_add_group_member_rejects_an_unknown_status(self):
        client = FakeClient()
        result = rock_build.add_group_member(
            {"modification": {"group_id": 1, "person_id": 2, "group_role_id": 3,
                              "status": "probationary"}}, client)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])

    def test_update_group_member_patches(self):
        client = FakeClient()
        result = rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"status": "inactive",
                                                                 "note": "moved away"}}},
            client)
        self.assertSucceeded(result)
        self.assertNoPut(client)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "GroupMembers/88", "params": None,
                          "data": {"GroupMemberStatus": 0, "Note": "moved away"}})

    def test_update_group_member_resolves_a_role_name(self):
        """A role arrives as a name and Rock wants an Id. Sending the name is a
        400, and it was what this operation did while the skill advertised
        "make him a leader"."""
        client = FakeClient(responses={
            "GroupMembers/88": {"Id": 88, "GroupId": 31},
            "Groups/31": {"Id": 31, "GroupTypeId": 25},
            "GroupTypeRoles": [{"Id": 7}],
        })
        result = rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"role": "Leader"}}},
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write(),
                         {"method": "PATCH", "endpoint": "GroupMembers/88", "params": None,
                          "data": {"GroupRoleId": 7}})

    def test_update_group_member_resolves_the_role_in_its_own_group(self):
        """Role names repeat across group types, so the membership's group has to
        be read back before the name means anything."""
        client = FakeClient(responses={
            "GroupMembers/88": {"Id": 88, "GroupId": 31},
            "Groups/31": {"Id": 31, "GroupTypeId": 25},
            "GroupTypeRoles": [{"Id": 7}],
        })
        rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"role": "Leader"}}},
            client)
        reads = [c["endpoint"] for c in client.calls if c["method"] == "GET"]
        self.assertEqual(reads[:2], ["GroupMembers/88", "Groups/31"])
        role_query = [c for c in client.calls if c["endpoint"] == "GroupTypeRoles"][0]
        self.assertIn("GroupTypeId eq 25", role_query["params"]["$filter"])

    def test_update_group_member_fails_when_the_role_is_unknown(self):
        client = FakeClient(responses={
            "GroupMembers/88": {"Id": 88, "GroupId": 31},
            "Groups/31": {"Id": 31, "GroupTypeId": 25},
            "GroupTypeRoles": [],
        })
        result = rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"role": "Hedgehog"}}},
            client)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])

    def test_update_group_member_takes_a_role_id_without_a_lookup(self):
        client = FakeClient()
        result = rock_build.update_group_member(
            {"modification": {"group_member_id": 88, "updates": {"group_role_id": 7}}},
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["data"], {"GroupRoleId": 7})
        self.assertEqual([c for c in client.calls if c["method"] == "GET"], [])

    def test_remove_group_member_deletes(self):
        client = FakeClient()
        result = rock_build.remove_group_member(
            {"modification": {"group_member_id": 88}}, client)
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
            client)
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
                              "data_view": "No Such View"}}, client)
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
            client)
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
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["params"],
                         {"attributeKey": "K", "attributeValue": "V"})

    def test_patch_is_allowed_without_ceremony(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PATCH", "endpoint": "Groups/31",
                         "body": {"Name": "Renamed"}}}, client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "PATCH")

    def test_put_is_refused_without_an_acknowledgement(self):
        """The whole point of the fix is that PUT replaces the entity. The
        escape hatch must not be a back door to the bug."""
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31",
                         "body": {"Name": "Renamed"}}}, client)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])
        self.assertIn("full_replace", result.failures[0]["error"])

    def test_put_is_allowed_with_an_acknowledgement(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31", "full_replace": True,
                         "body": {"Id": 31, "Name": "Renamed", "GroupTypeId": 25,
                                  "Guid": "0000", "CreatedDateTime": "2020-01-01"}}},
            client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "PUT")

    def test_a_delete_needs_no_body(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "DELETE", "endpoint": "GroupSyncs/12"}}, client)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["method"], "DELETE")

    def test_an_unknown_method_is_refused(self):
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "TRACE", "endpoint": "Groups/31"}}, client)
        self.assertFalse(result.success)
        self.assertEqual(client.calls, [])

    def test_an_absolute_url_is_refused(self):
        client = FakeClient()
        for endpoint in ("https://example.org/api/Groups",
                         "../../etc/passwd", "Groups/../../x"):
            result = rock_build.api_request(
                {"request": {"method": "POST", "endpoint": endpoint, "body": {}}},
                client)
            self.assertFalse(result.success, endpoint)
        self.assertEqual(client.calls, [])

    def test_a_patch_needs_a_body(self):
        """An empty PATCH changes nothing and reports success."""
        client = FakeClient()
        for body in (None, {}):
            result = rock_build.api_request(
                {"request": {"method": "PATCH", "endpoint": "Groups/31", "body": body}},
                client)
            self.assertFalse(result.success, repr(body))
        self.assertEqual(client.writes, [])

    def test_a_put_needs_a_body_even_when_acknowledged(self):
        """An empty PUT is the original bug in its purest form: Rock would null
        every column in the row. `full_replace` must not buy it."""
        client = FakeClient()
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31", "full_replace": True}},
            client)
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])

    def test_a_percent_encoded_traversal_is_refused(self):
        """`requests` passes %2e%2e through untouched and the server decodes it,
        so checking only the literal text is not enough."""
        client = FakeClient()
        for endpoint in ("Groups/%2e%2e/%2e%2e/x", "Groups/..%2fx", "Groups/%2e%2e"):
            result = rock_build.api_request(
                {"request": {"method": "DELETE", "endpoint": endpoint}}, client)
            self.assertFalse(result.success, endpoint)
        self.assertEqual(client.calls, [])

    def test_a_put_snapshots_the_entity_before_replacing_it(self):
        client = FakeClient(responses={"Groups/31": {"Id": 31, "Name": "Before"}})
        result = rock_build.api_request(
            {"request": {"method": "PUT", "endpoint": "Groups/31", "full_replace": True,
                         "body": {"Id": 31, "Name": "After"}}}, client)
        self.assertSucceeded(result)
        saved = sorted(rock_paths.SNAPSHOTS.glob("Groups-31-*.json"))
        self.assertTrue(saved, "a PUT must leave the previous entity on disk")
        self.assertIn("Before", saved[-1].read_text())

    def test_a_put_is_refused_when_the_entity_cannot_be_read(self):
        """No snapshot, no replace. Whatever stops the read also means nobody
        could undo the write."""
        client = FakeClient(fail_on={("GET", "Groups/31")})
        with self.assertRaises(rock_build.StepFailed) as stopped:
            rock_build.api_request(
                {"request": {"method": "PUT", "endpoint": "Groups/31",
                             "full_replace": True,
                             "body": {"Id": 31, "Name": "After"}}}, client)
        self.assertFalse(stopped.exception.result.success)
        self.assertEqual(client.writes, [])

    def test_a_missing_endpoint_is_refused(self):
        client = FakeClient()
        result = rock_build.api_request({"request": {"method": "POST"}}, client)
        self.assertFalse(result.success)


class TestWritePermission(unittest.TestCase):
    """rock.sh sets ROCK_ALLOW_WRITES; nothing else does."""

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

    def test_the_guard_runs_before_anything_reaches_rock(self):
        """One dispatch point, so one guard covers every operation.

        This used to be asserted by reading the text of `main` with
        `inspect.getsource` and comparing substring positions. Now it runs the
        dispatch: `connect` is what makes the login request, and refusing before
        it is called is the property that matters."""
        os.environ.pop("ROCK_ALLOW_WRITES", None)
        connected = []

        def connect():
            connected.append(True)
            raise AssertionError("the guard let a request through")

        with self.assertRaises(SystemExit) as caught:
            rock_build.run_plan({"operation": "create_group",
                                 "group": {"name": "Team", "group_type": "Small Group"}},
                                connect)
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(connected, [], "nothing may log in before the guard passes")


class TestPlanContract(WriteTestCase):
    """Every operation declares what its plan must carry, checked at dispatch.

    Two failures used to be invisible here. A missing key was a raw KeyError
    traceback, because eighteen of the nineteen handlers index their plan keys
    directly. And an empty `updates` on a PATCH was a request that changed
    nothing and reported success — five operations had no guard against it, and
    the three that did each wrote their own."""

    def setUp(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"

    def run_plan(self, plan, client=None, catalog=None):
        client = client if client is not None else FakeClient()
        result = rock_build.run_plan(plan, lambda: client, catalog or CATALOG)
        return result, client

    def test_every_operation_declares_its_requirements(self):
        self.assertEqual(set(rock_build.REQUIREMENTS), set(rock_build.OPERATIONS))

    def test_an_unknown_operation_never_builds_a_client(self):
        result = rock_build.run_plan({"operation": "delete_everything"},
                                     lambda: self.fail("connected anyway"))
        self.assertFalse(result.success)
        self.assertIn("unknown operation", result.failures[0]["error"])

    def test_every_operation_reports_a_plan_problem_rather_than_dispatching(self):
        """A bare `{"operation": ...}` names something every operation needs."""
        for operation in rock_build.OPERATIONS:
            with self.subTest(operation=operation):
                result, client = self.run_plan({"operation": operation})
                self.assertFalse(result.success)
                self.assertNotIn("unknown operation", result.failures[0]["error"])
                self.assertEqual(client.writes, [],
                                 "an incomplete plan must not send a request")

    EMPTY_BODY_PLANS = {
        "update_workflow": {"workflow_type_id": 12, "updates": {}},
        "update_activity": {"activity_type_id": 34, "updates": {}},
        "update_group": {"group_id": 31, "updates": {}},
        "update_group_member": {"group_member_id": 88, "updates": {}},
        "reorder_actions": {"action_order": []},
    }

    def test_an_empty_body_is_refused_rather_than_sent(self):
        for operation, modification in self.EMPTY_BODY_PLANS.items():
            with self.subTest(operation=operation):
                result, client = self.run_plan({"operation": operation,
                                                "modification": modification})
                self.assertFalse(result.success,
                                 "an empty body changes nothing and answers 200")
                self.assertEqual(client.writes, [])

    def test_update_action_still_allows_a_settings_only_change(self):
        result, client = self.run_plan({
            "operation": "update_action",
            "modification": {"action_type_id": 56, "settings": {"Order": "1"}},
        })
        self.assertSucceeded(result)
        self.assertEqual(client.writes[0]["endpoint"],
                         "WorkflowActionTypes/AttributeValue/56")

    def test_update_action_refuses_a_plan_that_changes_nothing(self):
        result, client = self.run_plan({
            "operation": "update_action",
            "modification": {"action_type_id": 56, "updates": {}, "settings": {}},
        })
        self.assertFalse(result.success)
        self.assertEqual(client.writes, [])

    def test_a_missing_key_is_a_named_failure_not_a_traceback(self):
        result, client = self.run_plan({"operation": "update_group",
                                        "modification": {"updates": {"name": "X"}}})
        self.assertFalse(result.success)
        self.assertIn("modification.group_id", result.failures[0]["error"])
        self.assertEqual(client.writes, [])

    def test_either_the_id_or_the_name_satisfies_a_pair(self):
        for modification in ({"group_id": 31, "person_id": 7, "role": "Member"},
                             {"group_id": 31, "person_id": 7, "group_role_id": 4}):
            with self.subTest(modification=modification):
                problems = rock_build.missing_requirements(
                    "add_group_member", {"modification": modification})
                self.assertEqual(problems, [])

    def test_neither_the_id_nor_the_name_names_both(self):
        problems = rock_build.missing_requirements(
            "add_group_member", {"modification": {"group_id": 31, "person_id": 7}})
        self.assertEqual(len(problems), 1)
        self.assertIn("modification.group_role_id", problems[0])
        self.assertIn("modification.role", problems[0])


class TestStepStopsThePlan(WriteTestCase):
    """A failed step records what failed and ends the plan.

    Thirty blocks in rock_build.py were the same four lines — try, except,
    record, return — differing only in two strings. Every one of them ended the
    handler, so ending the handler is the step's job, and a thirty-first block
    cannot forget the return."""

    def setUp(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"

    NEW_GROUP = {"operation": "create_group",
                 "group": {"name": "Ushers", "group_type_id": 15,
                           "settings": {"Nope": "x"}}}

    def test_the_plan_reports_what_landed_before_the_step_that_failed(self):
        client = FakeClient(fail_on={"Groups/AttributeValue/1001"})
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = rock_build.run_plan(self.NEW_GROUP, lambda: client, None)
        self.assertFalse(result.success)
        self.assertEqual([c["type"] for c in result.created], ["Group"])
        self.assertEqual([f["type"] for f in result.failures], ["Settings"])
        self.assertIn("1 of 2 entities created.", buffer.getvalue())

    def test_nothing_is_sent_after_the_step_that_failed(self):
        client = FakeClient(fail_on={"Groups/AttributeValue/1001"})
        with redirect_stdout(io.StringIO()):
            rock_build.run_plan(self.NEW_GROUP, lambda: client, None)
        self.assertEqual([c["endpoint"] for c in client.writes],
                         ["Groups", "Groups/AttributeValue/1001"])

    def test_a_step_that_succeeds_records_nothing(self):
        result = rock_build.BuildResult()
        with rock_build.step(result, "Group", "Ushers"):
            pass
        self.assertTrue(result.success)

    def test_a_nested_step_is_recorded_once(self):
        """`step` catches Exception, so it has to let its own signal through."""
        result = rock_build.BuildResult()
        with self.assertRaises(rock_build.StepFailed):
            with rock_build.step(result, "Outer", "outer"):
                with rock_build.step(result, "Inner", "inner"):
                    raise RuntimeError("Rock API HTTP 400")
        self.assertEqual([f["type"] for f in result.failures], ["Inner"])


class TestTheCatalogGate(WriteTestCase):
    """Only the operations that resolve a name need the catalog cache.

    Five of the nineteen do. All nineteen took a `catalog` argument, and the
    five were also written out by hand beside the operation table, where the
    list could disagree with the handlers in either direction: keep blocking an
    operation that had stopped resolving names, or hand no cache to one that had
    started."""

    def setUp(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"

    def test_an_operation_that_resolves_nothing_runs_without_a_catalog(self):
        client = FakeClient()
        result = rock_build.run_plan(
            {"operation": "update_group",
             "modification": {"group_id": 312, "updates": {"name": "Ushers"}}},
            lambda: client, None)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["endpoint"], "Groups/312")

    def test_an_operation_that_resolves_a_name_is_refused_without_one(self):
        result = rock_build.run_plan(
            {"operation": "add_action"},
            lambda: self.fail("connected with no catalog to resolve against"), None)
        self.assertFalse(result.success)
        self.assertIn("no catalog", result.failures[0]["error"])

    def test_no_handler_declares_a_catalog_it_never_reads(self):
        """The signature is the declaration, so an unread argument widens the gate."""
        for name, handler in rock_build.OPERATIONS.items():
            if "catalog" not in inspect.signature(handler).parameters:
                continue
            tree = ast.parse(textwrap.dedent(inspect.getsource(handler)))
            read = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            with self.subTest(operation=name):
                self.assertIn("catalog", read,
                              f"{name} takes a catalog it never reads, so the gate "
                              "asks for a cache it has no use for")


class TestFieldMapsAreClosed(WriteTestCase):
    """An unrecognised field is refused, not forwarded to Rock verbatim.

    All five maps ended `.get(key, key)`. That is the mechanism that sent a role
    *name* to `GroupRoleId` and had Rock answer 400 for a reason nobody reading
    the plan could see."""

    def setUp(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"

    UNKNOWN_FIELD_PLANS = {
        "update_workflow": {"workflow_type_id": 12, "updates": {"nope": 1}},
        "update_activity": {"activity_type_id": 34, "updates": {"nope": 1}},
        "update_action": {"action_type_id": 56, "updates": {"nope": 1}},
        "update_group": {"group_id": 31, "updates": {"nope": 1}},
        "update_group_member": {"group_member_id": 88, "updates": {"nope": 1}},
    }

    def test_an_unknown_field_is_refused_and_lists_what_is_accepted(self):
        for operation, modification in self.UNKNOWN_FIELD_PLANS.items():
            with self.subTest(operation=operation):
                client = FakeClient()
                result = rock_build.run_plan(
                    {"operation": operation, "modification": modification},
                    lambda: client, CATALOG)
                self.assertFalse(result.success)
                self.assertIn("unknown field", result.failures[0]["error"])
                self.assertIn("accepts:", result.failures[0]["error"])
                self.assertEqual(client.writes, [],
                                 "nothing may be forwarded to Rock")

    def test_a_role_name_can_no_longer_land_in_group_role_id(self):
        """The reported bug, as a test.

        `GROUP_MEMBER_FIELDS` was fixed by omitting `role`, but the passthrough
        that carried the name through was still there for every other key."""
        self.assertNotIn("role", rock_build.GROUP_MEMBER_FIELDS)
        with self.assertRaises(rock_build.PlanError):
            rock_build.rock_field(rock_build.GROUP_MEMBER_FIELDS, "role")

    def test_a_field_the_handler_resolves_itself_is_still_accepted(self):
        client = FakeClient(responses={
            "GroupMembers/88": {"Id": 88, "GroupId": 31},
            "Groups/31": {"Id": 31, "GroupTypeId": 9},
            "GroupTypeRoles": [{"Id": 4}],
        })
        result = rock_build.run_plan(
            {"operation": "update_group_member",
             "modification": {"group_member_id": 88, "updates": {"role": "Leader"}}},
            lambda: client, CATALOG)
        self.assertSucceeded(result)
        self.assertEqual(client.only_write()["data"], {"GroupRoleId": 4})


# ─────────────────────────────────────────────────────────────────────────────
# rock_query's four guarded writes
# ─────────────────────────────────────────────────────────────────────────────

class TestReportingHappensAtTheBoundary(WriteTestCase):
    """The handlers record what they did; `run_plan` prints it.

    Sixty-three calls to `report` used to sit inside the handlers, one beside
    all but six of the failure paths. Those six printed nothing themselves and
    were correct only because `apply_settings` had printed for them, so the
    answer to "which line produced this output" depended on which line failed."""

    def setUp(self):
        os.environ["ROCK_ALLOW_WRITES"] = "1"

    UPDATE = {"operation": "update_group",
              "modification": {"group_id": 312, "updates": {"name": "Ushers"}}}

    def plan_output(self, plan, client=None):
        client = client if client is not None else FakeClient()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = rock_build.run_plan(plan, lambda: client, CATALOG)
        return result, buffer.getvalue()

    def test_a_successful_plan_prints_one_report(self):
        result, output = self.plan_output(self.UPDATE)
        self.assertSucceeded(result)
        self.assertEqual(output.count("Build results:"), 1)

    def test_a_failed_handler_prints_one_report(self):
        result, output = self.plan_output(self.UPDATE,
                                         FakeClient(fail_on={"Groups/312"}))
        self.assertFalse(result.success)
        self.assertEqual(output.count("Build results:"), 1)

    def test_a_gate_refusal_prints_the_same_report(self):
        result, output = self.plan_output({"operation": "delete_everything"})
        self.assertFalse(result.success)
        self.assertEqual(output.count("Build results:"), 1)
        self.assertIn("Nothing was created.", output)

    def test_a_handler_called_directly_prints_nothing(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = rock_build.update_group(self.UPDATE, FakeClient())
        self.assertSucceeded(result)
        self.assertEqual(buffer.getvalue(), "",
                         "printing is the boundary's job, not the handler's")

    def test_a_second_failure_does_not_overwrite_the_first(self):
        result = rock_build.BuildResult()
        result.fail("Block", "first", "400")
        result.fail("Block", "second", "409")
        self.assertEqual([f["name"] for f in result.failures], ["first", "second"])

    def test_the_tally_counts_every_entity_the_plan_asked_for(self):
        """`len(created) + 1` assumed a single failure. Two made the total lie."""
        result = rock_build.BuildResult()
        result.add("Group", "Ushers", 312)
        result.fail("Block", "first", "400")
        result.fail("Block", "second", "409")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result.report()
        self.assertIn("1 of 3 entities created.", buffer.getvalue())


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

    def test_block_set_exits_non_zero_when_rock_rejects_the_key(self):
        """It printed the error and exited 0, so a skill reading the exit code
        saw a setting land that never did -- the fault it was fixed for."""
        client = FakeClient(responses={"Blocks/4821": {"Id": 4821}},
                            fail_on={("POST", "Blocks/AttributeValue/4821")})
        with self.assertRaises(SystemExit) as caught:
            rock_query.cmd_block_set(
                SimpleNamespace(id="4821", key="Nonsense", value="x"), client)
        self.assertNotEqual(caught.exception.code, 0)

    def test_block_set_exits_non_zero_when_the_block_is_missing(self):
        client = FakeClient()
        with self.assertRaises(SystemExit) as caught:
            rock_query.cmd_block_set(
                SimpleNamespace(id="4821", key="EnableDebug", value="false"), client)
        self.assertNotEqual(caught.exception.code, 0)

    def test_person_create_still_posts(self):
        client = FakeClient()
        rock_query.cmd_person_create(
            SimpleNamespace(first="A", last="B", email=None, connection_status=None,
                            record_status=None, campus=None), client)
        self.assertEqual(client.only_write()["method"], "POST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
