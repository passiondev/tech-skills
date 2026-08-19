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
import unittest
from contextlib import redirect_stdout
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
    """`tally` and `more_note` — the wording a capped collection prints."""

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

    def test_a_dropped_candidate_names_what_was_searched_for(self):
        self.assertIn("Smith", rock_query.more_note("Smith"))


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

    def test_several_matches_print_a_chooser_and_resolve_to_nothing(self):
        rows = [{"Id": 1, "Name": "Ushers A"}, {"Id": 2, "Name": "Ushers B"}]
        search = lambda flt, limit: (([], False) if "substringof" not in flt
                                     else (rows, False))
        out = io.StringIO()
        with redirect_stdout(out):
            found = rock_query._find_entity(FakeClient(), "Groups", "ush",
                                           label="group", search=search)
        self.assertIsNone(found, "an ambiguous reference must not pick for the operator")
        self.assertIn("Multiple groups match 'ush'", out.getvalue())
        self.assertIn("Ushers B", out.getvalue())

    def test_a_capped_chooser_says_more_match(self):
        rows = [{"Id": i, "Name": f"Ushers {i}"} for i in range(5)]
        search = lambda flt, limit: (([], False) if "substringof" not in flt
                                     else (rows, True))
        out = io.StringIO()
        with redirect_stdout(out):
            rock_query._find_entity(FakeClient(), "Groups", "ush", search=search)
        self.assertIn("and more match", out.getvalue())

    def test_nothing_found_says_so_and_names_the_kind(self):
        out = io.StringIO()
        with redirect_stdout(out):
            found = rock_query._find_entity(FakeClient(), "Groups", "nobody",
                                            label="check-in area")
        self.assertIsNone(found)
        self.assertIn("No check-in area found matching 'nobody'", out.getvalue())

    def test_the_label_defaults_to_the_endpoint(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rock_query._find_entity(FakeClient(), "Schedules", "nope")
        self.assertIn("No schedule found", out.getvalue())

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


if __name__ == "__main__":
    unittest.main()


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

    def test_a_command_that_printed_for_itself_renders_nothing(self):
        self.assertEqual(self.render(None), "")


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
