import http.client
import unittest
import urllib.error
from unittest import mock

from lib.live import INTERVAL_SECONDS, PageError, fetch_page, wait_until
from lib.registry import TIMEOUT_SECONDS, USER_AGENT
from tests.clock import Clock
from tests.registry_answers import Answer, failing


def page(title):
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head><body></body></html>"


class FetchPage(unittest.TestCase):
    def test_the_page_is_read_as_text(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(page("v0.1.0").encode())):
            self.assertEqual(fetch_page("https://example.org/"), page("v0.1.0"))

    def test_the_request_asks_for_a_fresh_copy_and_names_the_project(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(b"")) as urlopen:
            fetch_page("https://example.org/")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], TIMEOUT_SECONDS)

    def test_a_failed_answer_is_an_error(self):
        with failing(404), self.assertRaisesRegex(PageError, "answered 404"):
            fetch_page("https://example.org/")

    def test_a_site_that_cannot_be_reached_is_an_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
            with self.assertRaisesRegex(PageError, "cannot be reached: no route"):
                fetch_page("https://example.org/")

    def test_an_answer_cut_short_or_late_is_an_error(self):
        for error in (http.client.IncompleteRead(b"<"), TimeoutError("timed out")):
            with self.subTest(error=error), mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaisesRegex(PageError, "cannot be read"):
                    fetch_page("https://example.org/")


class WaitUntil(unittest.TestCase):
    def test_a_check_with_no_problem_runs_once_with_the_first_nonce(self):
        clock, nonces = Clock(), []
        problems = wait_until(lambda nonce: nonces.append(nonce) or [], clock.sleep, clock, 600, "5-1")
        self.assertEqual(problems, [])
        self.assertEqual(nonces, ["5-1-1"])
        self.assertEqual(clock.slept, [])

    def test_the_check_runs_again_with_a_new_nonce_until_it_has_no_problem(self):
        clock, nonces, answers = Clock(), [], iter([["stale"], ["stale"], []])
        problems = wait_until(lambda nonce: nonces.append(nonce) or next(answers), clock.sleep, clock, 600, "5-1")
        self.assertEqual(problems, [])
        self.assertEqual(nonces, ["5-1-1", "5-1-2", "5-1-3"])
        self.assertEqual(clock.slept, [INTERVAL_SECONDS, INTERVAL_SECONDS])

    def test_a_check_never_passing_returns_its_last_problems_at_the_timeout(self):
        clock, nonces = Clock(), []
        problems = wait_until(lambda nonce: nonces.append(nonce) or [f"stale {nonce}"], clock.sleep, clock, 100, "5-1")
        self.assertEqual(len(nonces), 100 // INTERVAL_SECONDS + 1)
        self.assertEqual(problems, [f"stale {nonces[-1]}"])
        self.assertLessEqual(sum(clock.slept), 100)


if __name__ == "__main__":
    unittest.main()
