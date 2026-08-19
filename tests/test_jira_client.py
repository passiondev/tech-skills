#!/usr/bin/env python3
"""Every Jira request this plugin makes, and what a person is told when it fails.

Four call sites each rolled their own curl and each knew a different subset of
the same four things. The failures that came of it are what these tests pin:

  * a curl that never ran read as status 0, and the operator was told "Jira
    returned 0" -- a number Jira had not returned, sending them to look at Jira
    for a fault on this side of the wire;
  * `project_exists` compared the status to the string "404", so every other
    failure -- an expired token, a proxy -- read as a project that is not there;
  * one script handled 403 and the other did not;
  * both spelled out their own wording for a 401, so the two drifted;
  * one attachment that would not download was recorded as a bare false, and
    the reason went nowhere;
  * the API token went to curl in `-u`, where `ps` shows it to every local user
    for as long as the request runs.

Run:  python3 -m unittest discover -s tests
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from jira_harness import (Garbage, Reply, TOKEN, Transport, client,
                          fetch_ticket, jira_client, sprint_report)


class TestWhatGoesOnTheWire(unittest.TestCase):
    """The request itself -- URL, verb, body, and what argv must never carry."""

    def test_a_get_hangs_off_the_one_api_version(self):
        c, curl = client(Reply(payload={"key": "ABC-1"}))
        c.get("issue/ABC-1")
        self.assertEqual(curl.calls[0].url,
                         "https://mycompany.atlassian.net/rest/api/3/issue/ABC-1")

    def test_a_trailing_slash_on_the_base_url_does_not_double(self):
        c, curl = client(Reply(payload={}))
        self.assertEqual(c.base_url, "https://mycompany.atlassian.net")
        c.get("/project/ABC")
        self.assertNotIn("//rest", curl.calls[0].url)

    def test_params_are_encoded_rather_than_pasted(self):
        c, curl = client(Reply(payload={}))
        c.get("search", params={"jql": "project = ABC AND assignee = me"})
        self.assertIn("jql=project+%3D+ABC+AND+assignee+%3D+me", curl.calls[0].url)

    def test_a_post_carries_its_body_as_json(self):
        c, curl = client(Reply(payload={"issues": []}))
        c.post("search/jql", {"jql": "project = ABC"})
        call = curl.calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.body, {"jql": "project = ABC"})
        self.assertIn("Content-Type: application/json", call.headers)

    def test_the_token_never_reaches_the_command_line(self):
        """`-u email:token` is readable in `ps` by every local user."""
        c, curl = client(Reply(payload={}), Reply(payload={}), Reply(200, "x"))
        c.get("issue/ABC-1")
        c.post("search/jql", {"jql": ""})
        with tempfile.TemporaryDirectory() as tmp:
            c.download("https://mycompany.atlassian.net/att/1",
                       Path(tmp) / "shot.png")
        for call in curl.calls:
            self.assertNotIn(TOKEN, " ".join(call.argv),
                             f"the token is in argv of {call.method} {call.url}")
            self.assertNotIn("-u", call.argv)
            self.assertIn(TOKEN, call.stdin, "curl still has to be told the token")

    def test_the_credentials_go_to_curl_as_a_config_file(self):
        self.assertEqual(jira_client._config_line("a@example.com", "sec"),
                         'user = "a@example.com:sec"\n')

    def test_a_quote_in_a_credential_is_escaped_rather_than_ending_the_value(self):
        line = jira_client._config_line('a"b', "back\\slash")
        self.assertEqual(line, 'user = "a\\"b:back\\\\slash"\n')


class TestHowAnAnswerIsRead(unittest.TestCase):
    """The status line, the body, and the two ways there is no answer at all."""

    def test_the_last_line_is_the_status_and_the_rest_is_the_body(self):
        c, _ = client(Reply(200, '{"key": "ABC-1"}'))
        self.assertEqual(c.get("issue/ABC-1"), {"key": "ABC-1"})

    def test_a_body_with_newlines_in_it_survives_the_split(self):
        c, _ = client(Reply(200, '{\n  "key": "ABC-1"\n}'))
        self.assertEqual(c.get("issue/ABC-1"), {"key": "ABC-1"})

    def test_an_empty_body_is_none_rather_than_a_crash(self):
        c, _ = client(Reply(204, ""))
        self.assertIsNone(c.get("issue/ABC-1"))

    def test_a_curl_that_never_ran_is_not_status_zero(self):
        """The bug: "Jira returned 0" named Jira for a local failure."""
        c, _ = client(Transport(7, "curl: (7) Failed to connect to host"))
        with self.assertRaises(jira_client.JiraUnreachable) as caught:
            c.get("issue/ABC-1")
        message = caught.exception.operator_message()
        self.assertIn("could not reach Jira", message)
        self.assertIn("curl exit 7", message)
        self.assertIn("Failed to connect", message, "curl's own words help")
        self.assertNotIn("returned 0", message)

    def test_curl_printing_no_status_line_is_unreachable_too(self):
        c, _ = client(Garbage("some proxy said no"))
        with self.assertRaises(jira_client.JiraUnreachable):
            c.get("issue/ABC-1")

    def test_a_two_hundred_carrying_html_is_a_named_failure(self):
        """A login redirect answers 200 with a page. json.loads would raise raw."""
        c, _ = client(Reply(200, "<html>Sign in</html>"))
        with self.assertRaises(jira_client.JiraError) as caught:
            c.get("issue/ABC-1")
        self.assertIn("not JSON", str(caught.exception))


class TestWhatEachStatusMeans(unittest.TestCase):
    """One class per outcome a caller has to tell apart, and one wording each."""

    def test_a_404_is_its_own_class_so_a_caller_can_catch_only_that(self):
        c, _ = client(Reply(404, payload={"errorMessages": ["Issue does not exist"]}))
        with self.assertRaises(jira_client.JiraNotFound):
            c.get("issue/ABC-9")

    def test_a_401_names_both_variables_and_the_file_they_live_in(self):
        c, _ = client(Reply(401, "<html>login</html>"))
        with self.assertRaises(jira_client.JiraAuthError) as caught:
            c.get("issue/ABC-1")
        message = caught.exception.operator_message()
        self.assertIn("JIRA_EMAIL", message)
        self.assertIn("JIRA_API_TOKEN", message)
        self.assertIn("passion.env", message)

    def test_a_403_says_permission_rather_than_credentials(self):
        c, _ = client(Reply(403, payload={"errorMessages": ["forbidden"]}))
        with self.assertRaises(jira_client.JiraAuthError) as caught:
            c.get("issue/ABC-1")
        message = caught.exception.operator_message()
        self.assertIn("403", message)
        self.assertIn("permission", message)
        self.assertNotIn("JIRA_API_TOKEN", message,
                         "a 403 is not a wrong token, and saying so sends "
                         "someone to reissue one that works")

    def test_any_other_status_carries_the_status_and_the_verb(self):
        c, _ = client(Reply(500, "boom"))
        with self.assertRaises(jira_client.JiraApiError) as caught:
            c.get("issue/ABC-1")
        self.assertEqual(caught.exception.status, 500)
        self.assertIn("500", caught.exception.operator_message())
        self.assertIn("GET issue/ABC-1", caught.exception.operator_message())

    def test_a_403_is_not_caught_by_a_handler_looking_for_a_missing_row(self):
        self.assertFalse(issubclass(jira_client.JiraAuthError,
                                    jira_client.JiraNotFound))
        self.assertTrue(issubclass(jira_client.JiraNotFound,
                                   jira_client.JiraError))


class TestWhatJiraSaidAboutAFailure(unittest.TestCase):
    """`_detail` -- the three shapes a Jira error body comes in."""

    def test_error_messages_are_joined(self):
        self.assertEqual(
            jira_client._detail('{"errorMessages": ["one", "two"]}'), "one; two")

    def test_a_field_error_map_names_the_field(self):
        self.assertEqual(
            jira_client._detail('{"errors": {"project": "is required"}}'),
            "project: is required")

    def test_html_falls_back_to_a_readable_prefix(self):
        detail = jira_client._detail("<html>\n  <body>Gateway Timeout</body>\n")
        self.assertIn("Gateway Timeout", detail)
        self.assertNotIn("\n", detail, "a multi-line page must not break the report")

    def test_a_long_page_is_cut_rather_than_printed_whole(self):
        self.assertEqual(len(jira_client._detail("x" * 5000)), 300)

    def test_a_json_body_that_is_not_an_object_still_reads(self):
        self.assertEqual(jira_client._detail("[1, 2]"), "[1, 2]")

    def test_an_empty_body_says_nothing_rather_than_none(self):
        self.assertEqual(jira_client._detail(""), "")


class TestTheOnePlaceAFailureStopsTheProgram(unittest.TestCase):
    """`api_errors_reported` -- entry points wrap their body in it; nothing else."""

    def test_a_jira_error_prints_its_operator_message_and_exits_one(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stderr(err):
            with jira_client.api_errors_reported():
                raise jira_client.JiraApiError(500, "GET", "issue/ABC-1", "boom")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("500", err.getvalue())

    def test_the_message_goes_to_stderr_because_stdout_carries_json(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out), redirect_stderr(err):
            with jira_client.api_errors_reported():
                raise jira_client.JiraError("nope")
        self.assertEqual(out.getvalue(), "",
                         "prose on stdout breaks anything parsing the ticket")
        self.assertIn("nope", err.getvalue())

    def test_a_timeout_says_how_long_it_waited(self):
        import io
        import subprocess
        from contextlib import redirect_stderr
        err = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stderr(err):
            with jira_client.api_errors_reported():
                raise subprocess.TimeoutExpired("curl", 30)
        self.assertIn("30s", err.getvalue())

    def test_an_unrelated_error_is_not_swallowed(self):
        with self.assertRaises(ZeroDivisionError):
            with jira_client.api_errors_reported():
                1 / 0


class TestFetchingOneTicket(unittest.TestCase):
    """`fetch_ticket` -- the 404 a reader has to be told two things about."""

    def test_the_ticket_comes_back_parsed(self):
        c, curl = client(Reply(payload={"key": "ABC-1", "fields": {}}))
        self.assertEqual(fetch_ticket.fetch_ticket(c, "ABC-1")["key"], "ABC-1")
        self.assertIn("fields=summary", curl.calls[0].url)

    def test_a_404_names_the_ticket_and_the_permission_it_could_also_be(self):
        c, _ = client(Reply(404, payload={"errorMessages": ["does not exist"]}))
        with self.assertRaises(jira_client.JiraError) as caught:
            fetch_ticket.fetch_ticket(c, "ABC-9")
        message = str(caught.exception)
        self.assertIn("ABC-9", message)
        self.assertIn("account", message, "Jira 404s for a ticket you cannot see")

    def test_a_404_stops_being_a_not_found_so_no_ladder_swallows_it(self):
        c, _ = client(Reply(404, ""))
        with self.assertRaises(jira_client.JiraError) as caught:
            fetch_ticket.fetch_ticket(c, "ABC-9")
        self.assertNotIsInstance(caught.exception, jira_client.JiraNotFound)

    def test_a_401_travels_up_untouched(self):
        c, _ = client(Reply(401, ""))
        with self.assertRaises(jira_client.JiraAuthError):
            fetch_ticket.fetch_ticket(c, "ABC-1")

    def test_a_two_hundred_with_no_ticket_in_it_is_a_named_failure(self):
        c, _ = client(Reply(204, ""))
        with self.assertRaises(jira_client.JiraError) as caught:
            fetch_ticket.fetch_ticket(c, "ABC-1")
        self.assertIn("ABC-1", str(caught.exception))


class TestTheAttachmentsOnATicket(unittest.TestCase):
    """`process_attachments` -- one image that will not come down is not the ticket."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.real_root = fetch_ticket.DOWNLOAD_ROOT
        fetch_ticket.DOWNLOAD_ROOT = Path(self.tmp.name)
        self.addCleanup(setattr, fetch_ticket, "DOWNLOAD_ROOT", self.real_root)

    def image(self, att_id, name):
        return {"id": att_id, "filename": name, "mimeType": "image/png",
                "size": 3, "content": f"https://mycompany.atlassian.net/att/{att_id}"}

    def test_an_image_is_downloaded_and_its_path_reported(self):
        c, _ = client(Reply(200, "PNG"))
        entries = fetch_ticket.process_attachments(
            c, [self.image("10", "shot.png")], "ABC-1")
        self.assertTrue(entries[0]["local_path"].endswith("10_shot.png"))
        self.assertEqual(Path(entries[0]["local_path"]).read_text(), "PNG")
        self.assertIsNone(entries[0]["download_error"])

    def test_the_id_prefixes_the_name_so_two_screenshots_do_not_collide(self):
        c, _ = client(Reply(200, "one"), Reply(200, "two"))
        entries = fetch_ticket.process_attachments(
            c, [self.image("10", "shot.png"), self.image("11", "shot.png")], "ABC-1")
        self.assertNotEqual(entries[0]["local_path"], entries[1]["local_path"])

    def test_one_failed_download_costs_that_image_and_nothing_else(self):
        c, _ = client(Reply(403, ""), Reply(200, "PNG"))
        entries = fetch_ticket.process_attachments(
            c, [self.image("10", "no.png"), self.image("11", "yes.png")], "ABC-1")
        self.assertIsNone(entries[0]["local_path"])
        self.assertIn("403", entries[0]["download_error"])
        self.assertTrue(entries[1]["local_path"], "the second image still came down")

    def test_a_failed_download_leaves_no_half_written_file_behind(self):
        """curl -o writes the error page to the file before the status is known."""
        c, _ = client(Reply(404, "<html>gone</html>"))
        entries = fetch_ticket.process_attachments(
            c, [self.image("10", "gone.png")], "ABC-1")
        self.assertIsNone(entries[0]["local_path"])
        self.assertEqual(list(Path(self.tmp.name).rglob("*.png")), [])

    def test_a_transport_failure_is_recorded_against_the_attachment(self):
        c, _ = client(Transport())
        entries = fetch_ticket.process_attachments(
            c, [self.image("10", "shot.png")], "ABC-1")
        self.assertIn("could not reach Jira", entries[0]["download_error"])

    def test_a_non_image_is_listed_and_never_fetched(self):
        c, curl = client()
        entries = fetch_ticket.process_attachments(c, [{
            "id": "12", "filename": "notes.pdf", "mimeType": "application/pdf",
            "size": 9, "content": "https://mycompany.atlassian.net/att/12"}], "ABC-1")
        self.assertFalse(entries[0]["is_image"])
        self.assertEqual(curl.calls, [], "downloading every attachment is not the job")

    def test_an_absent_attachment_field_is_no_attachments(self):
        c, _ = client()
        self.assertEqual(fetch_ticket.process_attachments(c, None, "ABC-1"), [])


class TestTheSprintQueue(unittest.TestCase):
    """`search` pages, and `project_exists` tells an empty sprint from a typo."""

    def test_every_page_is_read_not_just_the_first(self):
        """A single call silently drops the tail of a busy sprint."""
        c, curl = client(
            Reply(payload={"issues": [{"key": "ABC-1"}], "isLast": False,
                           "nextPageToken": "p2"}),
            Reply(payload={"issues": [{"key": "ABC-2"}], "isLast": True}))
        issues = sprint_report.search(c, "project = ABC")
        self.assertEqual([i["key"] for i in issues], ["ABC-1", "ABC-2"])
        self.assertEqual(curl.calls[0].body.get("nextPageToken"), None)
        self.assertEqual(curl.calls[1].body["nextPageToken"], "p2")

    def test_a_last_page_stops_the_loop_even_with_a_token(self):
        c, curl = client(Reply(payload={"issues": [], "isLast": True,
                                        "nextPageToken": "p2"}))
        sprint_report.search(c, "project = ABC")
        self.assertEqual(len(curl.calls), 1)

    def test_a_missing_project_reads_as_missing(self):
        c, _ = client(Reply(404, payload={"errorMessages": ["No project found"]}))
        self.assertFalse(sprint_report.project_exists(c, "NOPE"))

    def test_a_project_that_answers_exists(self):
        c, _ = client(Reply(payload={"key": "ABC"}))
        self.assertTrue(sprint_report.project_exists(c, "ABC"))

    def test_an_expired_token_is_not_reported_as_a_missing_project(self):
        """The shape this replaced compared the status to "404" as a string, so
        every other failure came out as a project that is not there."""
        c, _ = client(Reply(401, ""))
        with self.assertRaises(jira_client.JiraAuthError):
            sprint_report.project_exists(c, "ABC")

    def test_a_proxy_failure_is_not_reported_as_a_missing_project(self):
        c, _ = client(Transport())
        with self.assertRaises(jira_client.JiraUnreachable):
            sprint_report.project_exists(c, "ABC")


class TestTheCredentialsComeFromOnePlace(unittest.TestCase):
    """ADR 0005 -- environment first, then ~/.claude/passion.env."""

    def test_the_client_reads_the_three_variables_when_given_none(self):
        made = jira_client.JiraClient()
        self.assertEqual(made.base_url,
                         os.environ["JIRA_BASE_URL"].rstrip("/"))

    def test_explicit_credentials_win_over_the_environment(self):
        made = jira_client.JiraClient("https://example.com/", "a@example.com", "t")
        self.assertEqual(made.base_url, "https://example.com")

    def test_the_variable_names_match_what_passion_env_hints_at(self):
        for name in (jira_client.BASE_URL_ENV, jira_client.EMAIL_ENV,
                     jira_client.TOKEN_ENV):
            self.assertIn(name, jira_client.passion_env.HINTS,
                          f"{name} has no hint, so a missing one names no fix")


if __name__ == "__main__":
    unittest.main()
