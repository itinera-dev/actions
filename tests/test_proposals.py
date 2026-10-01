import unittest

from lib.proposals import acceptance_comment, proposal_numbers


class AcceptanceComment(unittest.TestCase):
    def test_the_comment_carries_the_merge_date_and_pull_request(self):
        self.assertEqual(acceptance_comment(18, "2026-10-01T22:41:07Z"), "Accepted on 2026-10-01 in #18.")


class ProposalNumbers(unittest.TestCase):
    def test_numbers_come_from_proposal_files(self):
        files = ["proposals/0002-foundations.md", "proposals/0012-local-executor.md"]
        self.assertEqual(proposal_numbers(files), [2, 12])

    def test_other_files_are_ignored(self):
        files = [
            "proposals/README.md",
            "proposals/TEMPLATE.md",
            "spec/01-concepts.md",
            "proposals/2-short.md",
            "proposals/0002-foundations.txt",
            "proposals/drafts/0003-rescue.md",
        ]
        self.assertEqual(proposal_numbers(files), [])

    def test_numbers_are_sorted_and_unique(self):
        files = ["proposals/0012-b.md", "proposals/0002-a.md", "proposals/0002-a.md"]
        self.assertEqual(proposal_numbers(files), [2, 12])


if __name__ == "__main__":
    unittest.main()
