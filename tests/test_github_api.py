import unittest
import urllib.request

from lib.github_api import SameHostAuthorization, next_page_url


class NextPageUrl(unittest.TestCase):
    def test_the_next_link_is_found_among_others(self):
        header = (
            '<https://api.github.com/x?page=2>; rel="next", '
            '<https://api.github.com/x?page=5>; rel="last"'
        )
        self.assertEqual(next_page_url(header), "https://api.github.com/x?page=2")

    def test_no_next_link_means_the_last_page(self):
        self.assertIsNone(next_page_url('<https://api.github.com/x?page=1>; rel="prev"'))
        self.assertIsNone(next_page_url(""))


class SameHostAuthorizationRedirects(unittest.TestCase):
    def redirect(self, to):
        request = urllib.request.Request(
            "https://api.github.com/repos/o/r/releases/assets/1", headers={"Authorization": "Bearer t"}
        )
        return SameHostAuthorization().redirect_request(request, None, 302, "Found", {}, to)

    def test_the_token_is_not_sent_to_another_host(self):
        self.assertFalse(self.redirect("https://objects.githubusercontent.com/x").has_header("Authorization"))

    def test_the_token_is_kept_on_the_same_host(self):
        self.assertTrue(self.redirect("https://api.github.com/repos/o/r/other").has_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
