import http.client
import unittest
import urllib.error
from unittest import mock

from lib.reference_live import (
    INTERVAL_SECONDS,
    PageError,
    fetch_page,
    live_pages,
    names_version,
    not_live,
    root_of,
    wait_until_live,
)
from lib.registry import TIMEOUT_SECONDS, USER_AGENT
from tests.registry_answers import Answer, failing


def page(title):
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head><body></body></html>"


class Clock:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class NamesVersion(unittest.TestCase):
    def test_a_title_naming_v_and_the_version_names_it(self):
        self.assertTrue(names_version(page("itinera - v0.1.0-beta.6"), "0.1.0-beta.6"))
        self.assertTrue(names_version(page("itinera/step | itinera - v0.1.0-beta.6"), "0.1.0-beta.6"))

    def test_an_earlier_version_does_not_name_it(self):
        self.assertFalse(names_version(page("itinera - v0.1.0-beta.5"), "0.1.0-beta.6"))

    def test_a_longer_version_starting_with_it_does_not_name_it(self):
        self.assertFalse(names_version(page("itinera - v0.1.0-beta.60"), "0.1.0-beta.6"))
        self.assertFalse(names_version(page("itinera - v0.1.0-beta.6.1"), "0.1.0-beta.6"))
        self.assertFalse(names_version(page("itinera - v0.1.0-beta"), "0.1.0-bet"))
        self.assertFalse(names_version(page("itinera - v0.1.0+build"), "0.1.0"))
        self.assertFalse(names_version(page("itinera - v1.0.0"), "1.0.0-rc.1"))

    def test_a_version_ending_a_sentence_names_it(self):
        self.assertTrue(names_version(page("The reference of v0.1.0."), "0.1.0"))

    def test_the_version_without_its_v_does_not_name_it(self):
        self.assertFalse(names_version(page("itinera - 0.1.0-beta.6"), "0.1.0-beta.6"))
        self.assertFalse(names_version(page("itinera - dev0.1.0"), "0.1.0"))

    def test_the_version_outside_the_title_does_not_name_it(self):
        self.assertFalse(names_version("<title>itinera</title><h1>v0.1.0</h1>", "0.1.0"))
        self.assertFalse(names_version("<h1>v0.1.0</h1>", "0.1.0"))

    def test_the_title_is_read_whatever_its_case_and_entities(self):
        self.assertTrue(names_version("<TITLE lang='en'>itinera &#45; v0.1.0</TITLE>", "0.1.0"))
        self.assertTrue(names_version("<title>v0.1.0&#x2D;rc.1</title>", "0.1.0-rc.1"))


class RootOf(unittest.TestCase):
    def test_the_root_ends_in_a_slash(self):
        self.assertEqual(root_of("https://example.org/ref/"), "https://example.org/ref/")
        self.assertEqual(root_of("https://example.org/ref"), "https://example.org/ref/")

    def test_anything_but_a_plain_web_address_is_refused(self):
        for url in ("", "itinera-dev.org/ref/", "ftp://example.org/", "https://example.org/?q=1", "https://x.org/#a"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "http or https address"):
                root_of(url)


class LivePages(unittest.TestCase):
    def test_the_root_and_the_release_front_page_are_checked(self):
        expected = ["https://example.org/ref/", "https://example.org/ref/0.1.0/"]
        self.assertEqual(live_pages("https://example.org/ref/", "0.1.0"), expected)


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


class NotLive(unittest.TestCase):
    pages = ["https://example.org/", "https://example.org/0.1.0/"]

    def test_pages_naming_the_version_are_live(self):
        self.assertEqual(not_live(self.pages, "0.1.0", lambda url: page("v0.1.0"), "1-1"), [])

    def test_each_page_is_read_with_the_nonce_in_its_query(self):
        read = []
        not_live(self.pages, "0.1.0", lambda url: read.append(url) or page("v0.1.0"), "7-2-3")
        self.assertEqual(read, ["https://example.org/?live-check=7-2-3", "https://example.org/0.1.0/?live-check=7-2-3"])

    def test_a_page_naming_another_version_or_unreadable_is_not_live(self):
        def fetch(url):
            if "/0.1.0/" in url:
                raise PageError("answered 404")
            return page("v0.0.9")

        problems = not_live(self.pages, "0.1.0", fetch, "1-1")
        self.assertEqual(
            problems,
            ["https://example.org/ does not name v0.1.0 in its title.", "https://example.org/0.1.0/ answered 404."],
        )


class WaitUntilLive(unittest.TestCase):
    pages = ["https://example.org/"]

    def test_a_live_reference_is_read_once(self):
        clock, read = Clock(), []
        problems = wait_until_live(
            self.pages, "0.1.0", lambda url: read.append(url) or page("v0.1.0"), clock.sleep, clock, 600, "5-1"
        )
        self.assertEqual(problems, [])
        self.assertEqual(read, ["https://example.org/?live-check=5-1-1"])
        self.assertEqual(clock.slept, [])

    def test_the_reference_is_read_again_with_a_new_nonce_until_it_is_live(self):
        clock, read, titles = Clock(), [], iter(["v0.0.9", "v0.0.9", "v0.1.0"])
        problems = wait_until_live(
            self.pages, "0.1.0", lambda url: read.append(url) or page(next(titles)), clock.sleep, clock, 600, "5-1"
        )
        self.assertEqual(problems, [])
        self.assertEqual(clock.slept, [INTERVAL_SECONDS, INTERVAL_SECONDS])
        self.assertEqual([url.rsplit("=", 1)[1] for url in read], ["5-1-1", "5-1-2", "5-1-3"])

    def test_a_timeout_shorter_than_the_interval_reads_once(self):
        clock, read = Clock(), []
        problems = wait_until_live(
            self.pages, "0.1.0", lambda url: read.append(url) or page("v0.0.9"), clock.sleep, clock, 0, "5-1"
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(len(read), 1)
        self.assertEqual(clock.slept, [])

    def test_a_reference_never_live_fails_at_the_timeout_with_the_last_reading(self):
        clock, read = Clock(), []
        problems = wait_until_live(
            self.pages, "0.1.0", lambda url: read.append(url) or page("v0.0.9"), clock.sleep, clock, 100, "5-1"
        )
        self.assertEqual(problems, ["https://example.org/ does not name v0.1.0 in its title."])
        self.assertEqual(len(read), 100 // INTERVAL_SECONDS + 1)
        self.assertLessEqual(sum(clock.slept), 100)
        self.assertEqual(read[-1], f"https://example.org/?live-check=5-1-{len(read)}")


if __name__ == "__main__":
    unittest.main()
