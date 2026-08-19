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

import unittest

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


if __name__ == "__main__":
    unittest.main()
