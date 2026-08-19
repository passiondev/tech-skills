#!/usr/bin/env python3
"""Every count the read side prints, asserted against what Rock actually held.

The bug these are written against is not a crash. `dataviews` printed
"Data Views (100)" on an instance holding more than ten times that, because the
header was `len()` of a `$top`-capped list. Nothing in the output said it was a
cap. Someone reads 100, believes it, and stops looking.

So the fix is not a bigger number, it is a fetch that knows it was capped.
`get_capped` asks Rock for one row more than it will show and reports whether
that row came back; `tally` turns the pair into a header that admits the
difference; `first` is the probe that wants one row and says so. These tests
pin all three, and `test_checks.py` pins the CI check that stops a fourth being
written.

Run:  python3 -m unittest discover -s tests
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock
from types import SimpleNamespace

from rock_harness import FakeClient, rock_query


class TestTheCappedFetch(unittest.TestCase):
    """`get_capped` — anything a person will see."""

    def _client(self, rows):
        return FakeClient(responses={"DataViews": rows})

    def test_a_full_page_reports_that_more_exist(self):
        client = self._client([{"Id": i} for i in range(6)])
        rows, more = rock_query.get_capped(client, "DataViews", {}, 5)
        self.assertEqual(len(rows), 5)
        self.assertTrue(more, "six rows came back for a limit of five — more exist")

    def test_a_short_page_reports_the_total(self):
        client = self._client([{"Id": i} for i in range(3)])
        rows, more = rock_query.get_capped(client, "DataViews", {}, 5)
        self.assertEqual(len(rows), 3)
        self.assertFalse(more)

    def test_it_asks_for_one_row_more_than_it_shows(self):
        client = self._client([])
        rock_query.get_capped(client, "DataViews", {"$select": "Id"}, 25)
        params = client.calls[0]["params"]
        self.assertEqual(params["$top"], 26,
                         "the extra row is what makes a cap visible without a count query")
        self.assertEqual(params["$select"], "Id", "the caller's params must survive")

    def test_an_answer_of_nothing_is_not_an_error(self):
        rows, more = rock_query.get_capped(FakeClient(), "DataViews", {}, 5)
        self.assertEqual((rows, more), ([], False))

    def test_a_row_exactly_on_the_limit_is_not_a_cap(self):
        client = self._client([{"Id": i} for i in range(5)])
        rows, more = rock_query.get_capped(client, "DataViews", {}, 5)
        self.assertEqual(len(rows), 5)
        self.assertFalse(more, "five of five is a total, not a cap")


class TestTheProbeFetch(unittest.TestCase):
    """`first` — is there one, and what is its id."""

    def test_a_probe_asks_for_a_single_row(self):
        client = FakeClient()
        rock_query.first(client, "Pages", {"$filter": "x"})
        self.assertEqual(client.calls[0]["params"]["$top"], 1)

    def test_a_probe_returns_the_row_itself(self):
        client = FakeClient(responses={"Pages": [{"Id": 7}, {"Id": 8}]})
        self.assertEqual(rock_query.first(client, "Pages", {}), {"Id": 7})

    def test_a_probe_returns_nothing_when_nothing_matched(self):
        self.assertIsNone(rock_query.first(FakeClient(), "Pages", {}))
        self.assertIsNone(rock_query.first(
            FakeClient(responses={"Pages": []}), "Pages", {}))


class TestTheCountAdmitsACap(unittest.TestCase):
    """`tally` — the wording a capped collection prints."""

    def test_an_uncapped_count_is_just_the_number(self):
        self.assertEqual(rock_query.tally([1, 2, 3], False), "3")

    def test_a_capped_count_says_more_exist_and_what_to_do(self):
        text = rock_query.tally([1, 2, 3], True)
        self.assertIn("more exist", text)
        self.assertIn("--limit", text, "a cap the reader cannot lift is half a message")

    def test_a_child_collection_names_its_own_remedy(self):
        text = rock_query.tally([1], True, hint=rock_query.CHILD_HINT)
        self.assertIn("no --limit", text,
                      "blocks on a page have no --limit to raise, so the hint differs")

    def test_a_chooser_names_the_two_ways_out(self):
        """`more_note` said this in a trailing line of its own. One caller had it,
        and both choosers say it in the header now."""
        text = rock_query.tally([1, 2], True, hint=rock_query.CHOOSER_HINT)
        self.assertIn("narrow it", text)
        self.assertIn("pass the ID", text)


class TestGroupsFetchedByType(unittest.TestCase):
    """`groups_of_types` — the same cap, past Rock's filter-size ceiling."""

    def _types(self, count):
        return list(range(100, 100 + count))

    def test_a_long_type_list_is_split_into_filters_rock_accepts(self):
        client = FakeClient()
        rock_query.groups_of_types(client, "substringof('a',Name)",
                                   self._types(40), 10)
        self.assertEqual(len(client.calls), 3, "40 types at 15 per filter is 3 requests")
        for call in client.calls:
            clauses = call["params"]["$filter"].count("GroupTypeId eq")
            self.assertLessEqual(clauses, rock_query.TYPE_CHUNK,
                                 "Rock answers 400 past 100 expression nodes")

    def test_the_type_restriction_travels_in_the_query(self):
        client = FakeClient()
        rock_query.groups_of_types(client, "substringof('a',Name)", [11], 10)
        self.assertIn("GroupTypeId eq 11", client.calls[0]["params"]["$filter"],
                      "filtering after the fetch spends the cap on discarded rows")

    def test_a_group_matched_by_two_chunks_is_counted_once(self):
        client = FakeClient(responses={"Groups": [{"Id": 5, "Name": "Ushers"}]})
        rows, more = rock_query.groups_of_types(client, "x", self._types(30), 10)
        self.assertEqual(rows, [{"Id": 5, "Name": "Ushers"}])
        self.assertFalse(more)

    def test_it_still_reports_more_beyond_the_limit(self):
        client = FakeClient(responses={
            "Groups": [{"Id": i, "Name": str(i)} for i in range(6)]})
        rows, more = rock_query.groups_of_types(client, "x", [11], 5)
        self.assertEqual(len(rows), 5)
        self.assertTrue(more)


class TestFindingOneEntity(unittest.TestCase):
    """`_find_entity` — the ladder every "name or ID" argument climbs."""

    def miss(self, *args, **kwargs):
        """The renderable the ladder raised, for a lookup that did not resolve."""
        with self.assertRaises(rock_query.LookupMiss) as caught:
            rock_query._find_entity(*args, **kwargs)
        return caught.exception.report

    def test_a_number_is_tried_as_an_id_first(self):
        client = FakeClient(responses={"Groups/7": {"Id": 7, "Name": "Ushers"}})
        found = rock_query._find_entity(client, "Groups", "7")
        self.assertEqual(found["Id"], 7)
        self.assertEqual(len(client.calls), 1, "a hit by ID asks Rock once")

    def test_an_exact_name_beats_a_substring(self):
        client = FakeClient(responses={"Groups": [{"Id": 3, "Name": "Ushers"}]})
        found = rock_query._find_entity(client, "Groups", "Ushers")
        self.assertEqual(found["Id"], 3)
        self.assertIn("Name eq 'Ushers'", client.calls[0]["params"]["$filter"])

    def test_a_single_substring_match_is_taken(self):
        calls = []

        def search(odata_filter, limit):
            calls.append(odata_filter)
            if "eq " in odata_filter and "substringof" not in odata_filter:
                return [], False
            return [{"Id": 9, "Name": "Ushers Team"}], False

        found = rock_query._find_entity(FakeClient(), "Groups", "ush", search=search)
        self.assertEqual(found["Id"], 9)

    def test_several_matches_are_a_chooser_and_not_a_pick(self):
        rows = [{"Id": 1, "Name": "Ushers A"}, {"Id": 2, "Name": "Ushers B"}]
        search = lambda flt, limit: (([], False) if "substringof" not in flt
                                     else (rows, False))
        chooser = self.miss(FakeClient(), "Groups", "ush", label="group",
                            search=search)
        self.assertEqual(chooser.title, "Multiple groups match 'ush'")
        self.assertEqual([r[0] for r in chooser.rows], [1, 2],
                         "an ambiguous reference must not pick for the operator")

    def test_a_capped_chooser_says_more_match(self):
        rows = [{"Id": i, "Name": f"Ushers {i}"} for i in range(5)]
        search = lambda flt, limit: (([], False) if "substringof" not in flt
                                     else (rows, True))
        chooser = self.miss(FakeClient(), "Groups", "ush", search=search)
        self.assertTrue(chooser.more, "a dropped candidate reads as not existing")
        self.assertIn("pass the ID", chooser.hint)

    def test_nothing_found_says_so_and_names_the_kind(self):
        report = self.miss(FakeClient(), "Groups", "nobody", label="check-in area")
        self.assertEqual(report.text, "No check-in area found matching 'nobody'")

    def test_the_label_defaults_to_the_endpoint(self):
        report = self.miss(FakeClient(), "Schedules", "nope")
        self.assertEqual(report.text, "No schedule found matching 'nope'")

    def test_a_command_lets_the_miss_travel_to_the_boundary(self):
        """Eleven commands wrote `if not x: return` after this call.

        A returned None left each of them to remember the guard, and left the
        boundary unable to tell a miss from an empty answer. The miss travels as
        an exception now, so the guards are gone and the boundary exits 1.
        """
        with self.assertRaises(rock_query.LookupMiss) as caught:
            rock_query.cmd_group(
                SimpleNamespace(identifier="typo", json=False, limit=50),
                FakeClient())
        self.assertEqual(caught.exception.report.text,
                         "No group found matching 'typo'")

    def test_a_caller_can_replace_the_search_without_editing_the_ladder(self):
        """The seam `checkin` needs: a name search restricted to group types."""
        asked = []

        def only_checkin_types(odata_filter, limit):
            asked.append(odata_filter)
            return [{"Id": 4, "Name": "Nursery"}], False

        found = rock_query._find_entity(FakeClient(), "Groups", "Nursery",
                                        search=only_checkin_types)
        self.assertEqual(found["Id"], 4)
        self.assertTrue(asked, "the replacement search must be the one that runs")


class TestWhatAnOperatorMeansByAPerson(unittest.TestCase):
    """`_people_filter` — one reading of a typed name, shared by two commands."""

    def test_an_address_is_matched_exactly(self):
        self.assertEqual(rock_query._people_filter("a@b.org"),
                         "Email eq 'a@b.org'")

    def test_two_words_are_a_first_and_last_name(self):
        self.assertEqual(rock_query._people_filter("Ada Lovelace"),
                         "FirstName eq 'Ada' and LastName eq 'Lovelace'")

    def test_a_middle_name_does_not_become_the_surname(self):
        self.assertIn("LastName eq 'Lovelace'",
                      rock_query._people_filter("Ada Byron Lovelace"))

    def test_one_word_is_a_surname(self):
        self.assertEqual(rock_query._people_filter("Lovelace"),
                         "LastName eq 'Lovelace'")

    def test_an_apostrophe_is_escaped_for_odata(self):
        self.assertIn("O''Brien", rock_query._people_filter("O'Brien"))


class TestAListingRendersItself(unittest.TestCase):
    """`Listing` — the rows a command found, and the one place they print."""

    def render(self, report):
        out = io.StringIO()
        with redirect_stdout(out):
            rock_query.render(report)
        return out.getvalue()

    def test_the_id_column_is_one_width_whoever_asks(self):
        listing = rock_query.Listing("Groups")
        listing.add(1, "one").add(1900412, "seven digits")
        lines = self.render(listing).splitlines()
        self.assertEqual(lines[2], "       1  one")
        self.assertEqual(lines[3], "  1900412  seven digits",
                         "a wider id widens its own row rather than truncating")

    def test_the_title_gives_the_count(self):
        listing = rock_query.Listing("Data Views")
        listing.add(7, "Active Adults")
        self.assertIn("Data Views (1):", self.render(listing))

    def test_a_capped_listing_says_so(self):
        listing = rock_query.Listing("Data Views", more=True)
        listing.add(7, "Active Adults")
        self.assertIn("first 1 — more exist, raise --limit", self.render(listing))

    def test_the_empty_line_comes_from_the_title(self):
        self.assertEqual(self.render(rock_query.Listing("Data Views")),
                         "No data views found.\n")

    def test_an_empty_listing_can_be_asked_to_say_nothing(self):
        self.assertEqual(self.render(rock_query.Listing("Pages", empty="")), "")

    def test_a_continuation_starts_where_the_label_does(self):
        listing = rock_query.Listing("Exceptions")
        listing.add(77012, "NullReferenceException", "Object reference not set")
        lines = self.render(listing).splitlines()
        self.assertEqual(lines[2].index("NullReference"),
                         lines[3].index("Object reference"))

    def test_an_empty_continuation_is_dropped(self):
        listing = rock_query.Listing("Exceptions")
        listing.add(1, "boom", "", None, "kept")
        self.assertEqual(len(self.render(listing).splitlines()), 4)

    def test_several_listings_are_separated(self):
        parts = [rock_query.Listing("Workflows"), rock_query.Listing("Groups")]
        parts[0].add(1, "a")
        parts[1].add(2, "b")
        self.assertIn("a\n\nGroups", self.render(parts))

    def test_returning_nothing_fails_loudly_rather_than_printing_nothing(self):
        """`render` has no `None` branch, and that is the point.

        A command that forgets to return would otherwise print nothing and exit
        0, which is the failure the renderables exist to make impossible.
        """
        with self.assertRaises(AttributeError):
            self.render(None)


class TestWhatAReadCommandReturns(unittest.TestCase):
    """The return value is the test surface -- no stdout, no string matching."""

    def test_workflows_carries_its_category_and_its_state(self):
        client = FakeClient(responses={
            "WorkflowTypes": [{"Id": 4821, "Name": "Serving Signup",
                               "IsActive": True, "CategoryId": 3},
                              {"Id": 91, "Name": "Old Flow", "IsActive": False}],
            "Categories/3": {"Name": "Volunteers"}})
        listing = rock_query.cmd_workflows(
            SimpleNamespace(category=None, limit=100), client)
        self.assertEqual([r[:2] for r in listing.rows],
                         [(4821, "Serving Signup (Volunteers)"),
                          (91, "Old Flow [inactive]")])

    def test_workflows_finding_nothing_is_an_empty_listing_not_a_none(self):
        listing = rock_query.cmd_workflows(
            SimpleNamespace(category=None, limit=100), FakeClient())
        self.assertEqual(listing.rows, [])

    def test_a_capped_fetch_reaches_the_listing(self):
        client = FakeClient(responses={
            "Schedules": [{"Id": i, "Name": f"s{i}", "IsActive": True}
                          for i in range(6)]})
        listing = rock_query.cmd_schedules(
            SimpleNamespace(active=False, query=None, limit=5), client)
        self.assertEqual(len(listing.rows), 5)
        self.assertTrue(listing.more)

    def test_a_page_with_no_internal_name_falls_back(self):
        client = FakeClient(responses={"Pages": [{"Id": 12, "PageTitle": "Give"},
                                                 {"Id": 13}]})
        listing = rock_query.cmd_pages(SimpleNamespace(site=None, limit=100), client)
        self.assertEqual([r[1] for r in listing.rows], ["Give", "(untitled)"])

    def test_search_returns_only_the_listings_that_held_something(self):
        client = FakeClient(responses={
            "WorkflowTypes": [{"Id": 4821, "Name": "Serving Signup"}],
            "Groups": [{"Id": 312, "Name": "Serving Team"}]})
        with redirect_stdout(io.StringIO()):
            parts = rock_query.cmd_search(SimpleNamespace(query="serving"), client)
        self.assertEqual([p.title for p in parts], ["Workflows", "Groups"])

    def test_search_finding_nothing_says_so_once(self):
        with redirect_stdout(io.StringIO()):
            report = rock_query.cmd_search(SimpleNamespace(query="zzz"), FakeClient())
        self.assertEqual(report.empty, "No results found.")

    def test_a_background_check_continues_onto_a_second_line(self):
        client = FakeClient(responses={"BackgroundChecks": [
            {"Id": 640, "RequestDate": "2026-07-02T00:00:00", "ResponseDate": None,
             "Status": "Pending"}]})
        listing = rock_query.cmd_bgc(
            SimpleNamespace(status=None, person=None, limit=50), client)
        self.assertEqual(listing.rows[0][2],
                         ["Requested: 2026-07-02  Responded: pending"])

    def test_a_null_comment_is_not_a_continuation(self):
        client = FakeClient(responses={"ConnectionRequests": [
            {"Id": 5501, "ConnectionState": 0, "Comments": None}]})
        listing = rock_query.cmd_connections(
            SimpleNamespace(state=None, opportunity=None, limit=50), client)
        self.assertEqual(len(listing.rows[0][2]), 1,
                         "a present-but-null Comments is not a line")

    def test_a_stack_trace_only_appears_when_it_was_asked_for(self):
        rows = [{"Id": 77012, "ExceptionType": "System.Boom",
                 "StackTrace": "at A()\nat B()"}]
        args = dict(type=None, summary=False, limit=50)
        quiet = rock_query.cmd_exceptions(
            SimpleNamespace(verbose=False, **args),
            FakeClient(responses={"ExceptionLogs": rows}))
        loud = rock_query.cmd_exceptions(
            SimpleNamespace(verbose=True, **args),
            FakeClient(responses={"ExceptionLogs": rows}))
        self.assertEqual(quiet.rows[0][2], [])
        self.assertEqual(loud.rows[0][2], ["at A()", "at B()"])


class TestADetailRendersItself(unittest.TestCase):
    """`Detail` and `Section` — one entity, and the one place it prints."""

    def render(self, report):
        out = io.StringIO()
        with redirect_stdout(out):
            rock_query.render(report)
        return out.getvalue()

    def test_a_heading_prints_at_the_margin(self):
        self.assertEqual(self.render(rock_query.Detail("Ushers (ID: 7)")),
                         "Ushers (ID: 7)\n")

    def test_a_field_sits_one_step_under_the_heading(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.field("Campus", "Downtown")
        self.assertEqual(self.render(detail).splitlines()[1], "  Campus: Downtown")

    def test_a_missing_value_adds_no_line(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.field("Email", None).field("Description", "")
        self.assertEqual(len(self.render(detail).splitlines()), 1,
                         "thirteen views wrote `if x.get(...)` around every line")

    def test_false_and_zero_are_answers_rather_than_absences(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.field("Active", False).field("Order", 0)
        self.assertIn("  Active: False", self.render(detail))
        self.assertIn("  Order: 0", self.render(detail),
                      "a group at order zero is at order zero")

    def test_a_deeper_line_sits_under_the_one_above_it(self):
        detail = rock_query.Detail("Ada Lovelace (ID: 31)")
        detail.field("Family", "Lovelace Family (ID: 88)")
        detail.line("Child      Byron Lovelace", depth=1)
        lines = self.render(detail).splitlines()
        self.assertEqual(lines[1].index("Family"), 2)
        self.assertEqual(lines[2].index("Child"), 4)

    def test_a_section_titles_itself_with_a_count(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.section("Members", [1, 2, 3]).add("Ada Lovelace")
        self.assertIn("  Members (3):", self.render(detail))

    def test_a_capped_section_says_more_exist(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.section("Members", [1], more=True).add("Ada Lovelace")
        self.assertIn("first 1 — more exist, raise --limit", self.render(detail))

    def test_a_child_section_names_the_remedy_it_actually_has(self):
        detail = rock_query.Detail("Give (ID: 12)")
        detail.section("Blocks", [1], more=True,
                       hint=rock_query.CHILD_HINT).add("Giving")
        self.assertIn("no --limit", self.render(detail),
                      "blocks on a page have no --limit to raise")

    def test_a_section_with_nothing_in_it_prints_nothing(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.section("Members", [])
        self.assertEqual(self.render(detail), "Ushers (ID: 7)\n",
                         "twelve commands guarded their own header instead")

    def test_a_section_can_have_no_count_at_all(self):
        detail = rock_query.Detail("Exception 5 (2026-08-01)")
        detail.section("Stack Trace").add("at A()")
        self.assertIn("  Stack Trace:", self.render(detail))

    def test_a_section_row_uses_the_one_id_column(self):
        detail = rock_query.Detail("Nursery (ID: 44)")
        detail.section("Sub-areas", [1]).row(1900412, "Toddlers")
        listing = rock_query.Listing("Groups")
        listing.add(1900412, "Toddlers")
        in_section = self.render(detail).splitlines()[-1]
        in_listing = self.render(listing).splitlines()[-1]
        self.assertEqual(in_section.strip(), in_listing.strip())
        self.assertTrue(in_section.startswith("    "),
                        "a section indents the column it shares")

    def test_a_blank_line_is_not_a_line(self):
        detail = rock_query.Detail("Ushers (ID: 7)")
        detail.line("").line(None)
        detail.section("Members", [1]).add("").add("Ada")
        self.assertEqual(len(self.render(detail).splitlines()), 3)

    def test_raw_prints_the_entity_rock_sent(self):
        text = self.render(rock_query.Raw({"Id": 7, "Name": "Ushers"}))
        self.assertEqual(json.loads(text), {"Id": 7, "Name": "Ushers"})
        self.assertIn("\n  ", text, "indented, so a person can read it too")

    def test_text_prints_what_it_holds(self):
        self.assertEqual(self.render(rock_query.Text("Block 9 not found")),
                         "Block 9 not found\n")


class TestWhatADetailViewReturns(unittest.TestCase):
    """Thirteen views that printed. The return value is the test surface."""

    def test_a_group_carries_its_type_campus_and_roster(self):
        client = FakeClient(responses={
            "Groups/7": {"Id": 7, "Name": "Ushers", "GroupTypeId": 4,
                         "IsActive": True, "CampusId": 2},
            "GroupTypes/4": {"Name": "Serving Team"},
            "Campuses/2": {"Name": "Downtown"},
            "GroupMembers": [{"PersonId": 31, "GroupRoleId": 9,
                              "GroupMemberStatus": 1}],
            "GroupTypeRoles/9": {"Name": "Leader"},
            "People/31": {"FirstName": "Ada", "LastName": "Lovelace"}})
        detail = rock_query.cmd_group(
            SimpleNamespace(identifier="7", json=False, limit=50), client)
        self.assertEqual(detail.heading, "Ushers (ID: 7)")
        self.assertIn("Type: Serving Team", [p for _, p in detail.parts
                                             if isinstance(p, str)])
        roster = [p for _, p in detail.parts if isinstance(p, rock_query.Section)][0]
        self.assertEqual(roster.title, "Members")
        self.assertIn("Ada Lovelace", roster.lines[0][1])
        self.assertIn("[Active]", roster.lines[0][1])

    def test_an_unresolved_lookup_leaves_the_field_out(self):
        """`_resolve_name` answers "?" for a row it could not read.

        The guard is at the call site rather than in `field`, so "?" stays a
        thing only the resolver says.
        """
        client = FakeClient(responses={
            "Groups/7": {"Id": 7, "Name": "Ushers", "CampusId": 2}})
        self.assertEqual(rock_query._resolve_name(client, "Campuses", 2, "Name"),
                         "?")
        detail = rock_query.cmd_group(
            SimpleNamespace(identifier="7", json=False, limit=50), client)
        fields = [p for _, p in detail.parts if isinstance(p, str)]
        self.assertEqual([f for f in fields if f.endswith(": ?")], [],
                         f"a field the resolver could not fill: {fields}")

    def test_json_answers_with_the_entity_and_fetches_nothing_further(self):
        client = FakeClient(responses={"Groups/7": {"Id": 7, "Name": "Ushers"}})
        report = rock_query.cmd_group(
            SimpleNamespace(identifier="7", json=True, limit=50), client)
        self.assertEqual(report.entity, {"Id": 7, "Name": "Ushers"})
        self.assertEqual(len(client.calls), 1,
                         "a roster nobody will print is a request nobody needs")

    def test_a_person_nests_their_family_under_the_family_line(self):
        client = FakeClient(responses={
            "People/31": {"Id": 31, "FirstName": "Ada", "LastName": "Lovelace"},
            "Groups/GetFamilies/31": [{"Id": 88, "Name": "Lovelace Family"}],
            "GroupMembers": [{"PersonId": 31, "GroupRoleId": 3},
                             {"PersonId": 32, "GroupRoleId": 4}],
            "GroupTypeRoles/3": {"Name": "Adult"},
            "GroupTypeRoles/4": {"Name": "Child"},
            "People/32": {"FirstName": "Byron", "LastName": "Lovelace"}})
        detail = rock_query.cmd_person(SimpleNamespace(identifier="31"), client)
        depths = [(depth, text) for depth, text in detail.parts
                  if isinstance(text, str)]
        self.assertEqual(depths[0], (0, "Family: Lovelace Family (ID: 88)"))
        self.assertEqual(depths[1][0], 1, "a member sits under their family")
        self.assertIn("Byron Lovelace", depths[1][1])
        self.assertNotIn("Ada", depths[1][1], "the person is not their own relative")

    def person_miss(self, client):
        """What `person` raised, for a name that did not resolve to one person."""
        with self.assertRaises(rock_query.LookupMiss) as caught:
            rock_query.cmd_person(SimpleNamespace(identifier="Ada"), client)
        return caught.exception.report

    def test_several_people_are_a_chooser_and_not_a_pick(self):
        listing = self.person_miss(FakeClient(responses={"People": [
            {"Id": 31, "FirstName": "Ada", "LastName": "Lovelace"},
            {"Id": 32, "FirstName": "Ada", "LastName": "Byron"}]}))
        self.assertEqual([r[0] for r in listing.rows], [31, 32])
        self.assertIn("Ada", listing.title)

    def test_a_capped_chooser_says_how_to_narrow_it(self):
        listing = self.person_miss(FakeClient(responses={"People": [
            {"Id": i, "FirstName": "Ada", "LastName": str(i)} for i in range(11)]}))
        self.assertTrue(listing.more)
        self.assertIn("pass the ID", listing.hint)

    def test_nobody_matching_is_a_miss_carrying_a_sentence(self):
        with self.assertRaises(rock_query.LookupMiss) as caught:
            rock_query.cmd_person(SimpleNamespace(identifier="zzz"), FakeClient())
        self.assertEqual(caught.exception.report.text,
                         "No person found matching 'zzz'")

    def test_a_page_groups_its_blocks_by_zone(self):
        client = FakeClient(responses={
            "Pages/12": {"Id": 12, "InternalName": "Give", "LayoutId": 3},
            "Blocks": [{"Id": 1, "Name": "Giving", "Zone": "Main", "BlockTypeId": 5},
                       {"Id": 2, "Name": None, "Zone": "Footer", "BlockTypeId": 6}],
            "BlockTypes/5": {"Name": "Transaction Entry"},
            "BlockTypes/6": {"Name": "Html Content"},
            "PageRoutes": [{"Route": "give"}]})
        detail = rock_query.cmd_page(
            SimpleNamespace(identifier="12", json=False), client)
        blocks = [p for _, p in detail.parts if isinstance(p, rock_query.Section)][0]
        self.assertEqual([d for d, _ in blocks.lines], [0, 1, 0, 1],
                         "a zone heading sits above the blocks in it")
        self.assertIn("Zone: Main", blocks.lines[0][1])
        self.assertIn("Html Content [Html Content]", blocks.lines[3][1],
                      "an unnamed block falls back to its type")

    def test_an_exception_keeps_its_trace_and_its_inner_cause(self):
        client = FakeClient(responses={
            "ExceptionLogs/77012": {
                "Id": 77012, "ExceptionType": "System.NullReferenceException",
                "StackTrace": "  at A()\n  at B()", "HasInnerException": True},
            "ExceptionLogs": [{"Id": 77013, "ExceptionType": "System.Inner",
                               "Description": "the real cause"}]})
        detail = rock_query.cmd_exception(
            SimpleNamespace(id=77012, json=False), client)
        trace = [p for _, p in detail.parts if isinstance(p, rock_query.Section)][0]
        self.assertEqual([t for _, t in trace.lines], ["at A()", "at B()"])
        deeper = [(d, t) for d, t in detail.parts if isinstance(t, str) and d]
        self.assertEqual(deeper, [(1, "the real cause")])

    def test_an_exception_that_is_gone_says_so(self):
        report = rock_query.cmd_exception(
            SimpleNamespace(id=1, json=False), FakeClient())
        self.assertEqual(report.text, "Exception 1 not found")

    def test_the_exception_summary_counts_by_short_type(self):
        rows = [{"Id": 1, "ExceptionType": "System.NullReferenceException"},
                {"Id": 2, "ExceptionType": "System.NullReferenceException"},
                {"Id": 3, "ExceptionType": "System.TimeoutException"}]
        summary = rock_query.cmd_exceptions(
            SimpleNamespace(type=None, summary=True, verbose=False, limit=50),
            FakeClient(responses={"ExceptionLogs": rows}))
        lines = [text for _, text in summary.parts]
        self.assertEqual(lines, ["   2  NullReferenceException",
                                 "   1  TimeoutException"])
        self.assertIn("3 most recent", summary.heading,
                      "the window is the rows fetched, not the log")

    def test_a_capped_summary_says_the_window_is_a_cap(self):
        rows = [{"Id": i, "ExceptionType": "System.Boom"} for i in range(4)]
        summary = rock_query.cmd_exceptions(
            SimpleNamespace(type=None, summary=True, verbose=False, limit=3),
            FakeClient(responses={"ExceptionLogs": rows}))
        self.assertIn("of more", summary.heading)

    def test_attendee_names_only_appear_when_asked_for(self):
        responses = {
            "AttendanceOccurrences/5": {"Id": 5, "OccurrenceDate": "2026-08-16"},
            "Attendances": [{"PersonAliasId": 88, "DidAttend": True}],
            "PersonAlias/88": {"PersonId": 31},
            "People/31": {"FirstName": "Ada", "LastName": "Lovelace"}}
        args = dict(id=5, json=False, limit=200)
        quiet = rock_query.cmd_occurrence(SimpleNamespace(names=False, **args),
                                         FakeClient(responses=responses))
        loud = rock_query.cmd_occurrence(SimpleNamespace(names=True, **args),
                                        FakeClient(responses=responses))
        self.assertEqual([t for _, t in quiet.parts],
                         ["Attendees: 1 attended / 1 total"])
        self.assertIn("Ada Lovelace", loud.parts[-1][1])

    def test_a_check_in_area_lists_its_locations_and_sub_areas(self):
        client = FakeClient(responses={
            "GroupTypes": [{"Id": 20, "Name": "Check-in by Age"}],
            "Groups": [{"Id": 44, "Name": "Nursery", "IsActive": True}],
            "GroupLocations": [{"LocationId": 61}],
            "Locations/61": {"Name": "Room 101"}})
        detail = rock_query.cmd_checkin(SimpleNamespace(area="Nursery"), client)
        sections = [p for _, p in detail.parts
                    if isinstance(p, rock_query.Section)]
        self.assertEqual([s.title for s in sections], ["Locations", "Sub-areas"])
        self.assertIn("Room 101 (ID: 61)", sections[0].lines[0][1])

    def test_a_workflow_with_no_attributes_names_the_workflow(self):
        client = FakeClient(responses={
            "WorkflowTypes/4821": {"Id": 4821, "Name": "Serving Signup"}})
        report = rock_query.cmd_attributes(
            SimpleNamespace(identifier="4821"), client)
        self.assertEqual(report.text,
                         "No attributes on 'Serving Signup' (ID: 4821)")

    def test_an_audit_answers_with_the_tree_and_both_lists(self):
        wf = {"Id": 4821, "Name": "Serving Signup", "IsActive": True,
              "ActivityTypes": [{"Id": 1, "Name": "Start", "Order": 0,
                                 "IsActivatedWithWorkflow": True,
                                 "ActionTypes": []}]}
        report = rock_query._audit_report(wf, ["no actions"], ["unreachable"])
        self.assertIn("Issues (1):", report.text)
        self.assertIn("✗ no actions", report.text)
        self.assertIn("! unreachable", report.text)

    def test_an_audit_that_found_nothing_says_that_instead(self):
        wf = {"Id": 4821, "Name": "Serving Signup", "IsActive": True}
        report = rock_query._audit_report(wf, [], [])
        self.assertIn("✓ No issues found", report.text)
        self.assertNotIn("Issues (0)", report.text)

    def test_the_check_in_hierarchy_comes_back_as_a_tree(self):
        client = FakeClient(responses={
            "GroupTypes": [{"Id": 20, "Name": "Check-in by Age"}],
            "Groups": []})
        report = rock_query.cmd_checkin(SimpleNamespace(area=None), client)
        self.assertIn("Group Type: Check-in by Age (ID: 20)", report.text)

    def test_no_check_in_group_types_is_a_sentence(self):
        report = rock_query.cmd_checkin(SimpleNamespace(area=None), FakeClient())
        self.assertEqual(report.text, "No check-in group types found.")


class TestWhatTheBoundaryDoesWithAnAnswer(unittest.TestCase):
    """`main` — what reaches stdout, and what the exit code says about it.

    The footnote in a0d8743 left one question open: a lookup that matched
    nothing exited 0, and making every empty answer exit non-zero would be wrong
    for `workflows` on an instance holding none. The renderables answer it. A
    name that does not resolve raises `LookupMiss` and exits 1; a collection that
    is genuinely empty is a `Listing` with no rows and exits 0. Both reach this
    boundary, and they reach it by different routes.
    """

    def run_cli(self, *argv, responses=None, client=None):
        client = client or FakeClient(responses=responses or {})
        out, status = io.StringIO(), 0
        argv = ["rock_query.py", *argv]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(rock_query, "RockClient", lambda: client), \
             redirect_stdout(out):
            try:
                rock_query.main()
            except SystemExit as stop:
                status = stop.code
        return status, out.getvalue()

    def test_an_answer_prints_once_and_exits_zero(self):
        status, out = self.run_cli("group", "7", responses={
            "Groups/7": {"Id": 7, "Name": "Ushers", "IsActive": True}})
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines()[0], "Ushers (ID: 7)")

    def test_a_name_that_resolves_to_nothing_exits_one(self):
        status, out = self.run_cli("group", "typo")
        self.assertEqual(status, 1, "naming a thing that is not there is a "
                                   "failed request, not an empty answer")
        self.assertEqual(out, "No group found matching 'typo'\n")

    def test_a_name_that_resolves_to_several_things_exits_one(self):
        class OnlyOnSubstring(FakeClient):
            """Answers the ladder's substring step and not its exact-name step.

            `FakeClient` replies from an endpoint table and ignores the filter,
            so without this the exact step matches and the chooser never opens.
            """

            def get(self, endpoint, params=None, timeout=30):
                if "substringof" not in (params or {}).get("$filter", ""):
                    self._record("GET", endpoint, params=params)
                    return []
                return super().get(endpoint, params=params, timeout=timeout)

        status, out = self.run_cli("group", "Ush", client=OnlyOnSubstring(
            responses={"Groups": [{"Id": 1, "Name": "Ushers A"},
                                  {"Id": 2, "Name": "Ushers B"}]}))
        self.assertEqual(status, 1)
        self.assertIn("Multiple groups match 'Ush' (2):", out)
        self.assertIn("Ushers B", out)

    def test_a_collection_that_is_genuinely_empty_exits_zero(self):
        status, out = self.run_cli("workflows")
        self.assertEqual(status, 0, "an instance holding no workflows was asked "
                                   "and answered")
        self.assertEqual(out, "No workflows found.\n")

    def test_a_write_command_reached_the_wrong_way_exits_two(self):
        """`_guard_writes` runs before the client is built. See ADR 0016."""
        status, out = self.run_cli("person-update", "31", "Email=a@example.com")
        self.assertEqual(status, 2)
        self.assertEqual(out, "", "the refusal goes to stderr")


if __name__ == "__main__":
    unittest.main()
