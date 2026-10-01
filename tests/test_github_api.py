import unittest

from lib.github_api import next_page_url


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


if __name__ == "__main__":
    unittest.main()
