import unittest

from lib.live import PageError, wait_until
from lib.site_live import file_url, not_live
from tests.clock import Clock

URL = "https://example.org/book/editions.json"
BUILT = '{"editions":[{"source":"main","commit":"3badbb8"}]}'


class FileUrl(unittest.TestCase):
    def test_a_plain_address_of_a_file_is_kept(self):
        self.assertEqual(file_url(URL), URL)

    def test_anything_but_a_plain_web_address_is_refused(self):
        for url in ("", "itinera-dev.org/x.json", "ftp://example.org/x.json", f"{URL}?q=1", f"{URL}#a"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "http or https address"):
                file_url(url)

    def test_a_directory_is_refused(self):
        with self.assertRaisesRegex(ValueError, "must name a file"):
            file_url("https://example.org/book/")


class NotLive(unittest.TestCase):
    def test_a_file_holding_what_the_build_wrote_is_live(self):
        self.assertEqual(not_live(URL, BUILT, lambda url: BUILT, "1-1"), [])

    def test_white_space_around_either_is_ignored(self):
        self.assertEqual(not_live(URL, f"{BUILT}\n", lambda url: f"  {BUILT}\n\n", "1-1"), [])

    def test_the_file_is_read_with_the_nonce_in_its_query(self):
        read = []
        not_live(URL, BUILT, lambda url: read.append(url) or BUILT, "7-2-3")
        self.assertEqual(read, [f"{URL}?live-check=7-2-3"])

    def test_a_file_holding_what_an_earlier_build_wrote_is_not_live(self):
        earlier = BUILT.replace("3badbb8", "58751b3")
        self.assertEqual(
            not_live(URL, BUILT, lambda url: earlier, "1-1"), [f"{URL} does not hold what the deployed build wrote."]
        )

    def test_a_file_that_cannot_be_read_is_not_live(self):
        def fetch(url):
            raise PageError("answered 404")

        self.assertEqual(not_live(URL, BUILT, fetch, "1-1"), [f"{URL} answered 404."])


class WaitingForTheSite(unittest.TestCase):
    def test_the_file_is_read_again_until_it_holds_what_the_build_wrote(self):
        clock, bodies = Clock(), iter(["{}", "{}", BUILT])
        problems = wait_until(
            lambda attempt: not_live(URL, BUILT, lambda url: next(bodies), attempt), clock.sleep, clock, 600, "5-1"
        )
        self.assertEqual(problems, [])
        self.assertEqual(len(clock.slept), 2)


if __name__ == "__main__":
    unittest.main()
