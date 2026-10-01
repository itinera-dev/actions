import unittest

from lib.closing import cross_repo_closings

REPO = "itinera-dev/spec"


class CrossRepoClosings(unittest.TestCase):
    def test_closing_an_issue_in_the_same_repository_is_allowed(self):
        self.assertEqual(cross_repo_closings("Closes #4", REPO), [])
        self.assertEqual(cross_repo_closings("Closes itinera-dev/spec#4", REPO), [])

    def test_the_repository_comparison_ignores_case(self):
        self.assertEqual(cross_repo_closings("closes: Itinera-Dev/Spec#3", REPO), [])

    def test_closing_another_repositorys_issue_is_reported(self):
        self.assertEqual(
            cross_repo_closings("Fixes itinera-dev/itinera-rs#2", REPO),
            ["Fixes itinera-dev/itinera-rs#2"],
        )

    def test_issue_urls_count_as_references(self):
        text = "resolves https://github.com/itinera-dev/itinera-rs/issues/9"
        self.assertEqual(cross_repo_closings(text, REPO), [text])

    def test_every_keyword_form_is_recognised(self):
        for keyword in ("close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved"):
            with self.subTest(keyword=keyword):
                self.assertEqual(len(cross_repo_closings(f"{keyword} other/repo#1", REPO)), 1)

    def test_refs_is_not_a_closing_keyword(self):
        self.assertEqual(cross_repo_closings("Refs itinera-dev/itinera-rs#2", REPO), [])

    def test_a_keyword_inside_another_word_does_not_count(self):
        self.assertEqual(cross_repo_closings("encloses other/repo#1", REPO), [])

    def test_every_offending_reference_is_reported(self):
        text = "Closes other/repo#1\nand fixes another/repo#2"
        self.assertEqual(len(cross_repo_closings(text, REPO)), 2)


if __name__ == "__main__":
    unittest.main()
