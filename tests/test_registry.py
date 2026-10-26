import http.client
import unittest
import urllib.error
from unittest import mock

from lib.registry import TIMEOUT_SECONDS, USER_AGENT, RegistryError, get_json
from tests.registry_answers import Answer, answering, failing


class GetJson(unittest.TestCase):
    def test_the_answer_is_read_as_json(self):
        with answering({"versions": []}):
            self.assertEqual(get_json("https://example.org/x"), {"versions": []})

    def test_nothing_there_is_none(self):
        with failing(404):
            self.assertIsNone(get_json("https://example.org/x"))

    def test_any_other_failure_is_an_error(self):
        with failing(500), self.assertRaisesRegex(RegistryError, "failed with 500: why"):
            get_json("https://example.org/x")

    def test_a_registry_that_cannot_be_reached_is_an_error(self):
        unreachable = urllib.error.URLError("no route")
        with mock.patch("urllib.request.urlopen", side_effect=unreachable):
            with self.assertRaisesRegex(RegistryError, "failed: no route"):
                get_json("https://example.org/x")

    def test_a_registry_that_does_not_answer_in_time_is_an_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(RegistryError, "failed: timed out"):
                get_json("https://example.org/x")

    def test_an_answer_cut_short_is_an_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"{")):
            with self.assertRaisesRegex(RegistryError, "failed: IncompleteRead"):
                get_json("https://example.org/x")

    def test_the_request_gives_up_after_a_while(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(b"{}")) as urlopen:
            get_json("https://example.org/x")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], TIMEOUT_SECONDS)

    def test_an_answer_that_is_not_json_is_an_error(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(b"<html>")):
            with self.assertRaisesRegex(RegistryError, "did not answer with JSON"):
                get_json("https://example.org/x")

    def test_the_request_names_the_project_as_its_user_agent(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(b"{}")) as urlopen:
            get_json("https://example.org/x", "application/vnd.npm.install-v1+json")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(request.get_header("Accept"), "application/vnd.npm.install-v1+json")
        self.assertNotIn("@", USER_AGENT)


if __name__ == "__main__":
    unittest.main()
