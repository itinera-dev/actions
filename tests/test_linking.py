import unittest

from lib.linking import Issue, problems

READY = {"proposal", "status: ready"}


class DefaultProfile(unittest.TestCase):
    def test_an_open_linked_issue_is_enough(self):
        self.assertEqual(problems("default", [Issue(5, True)], []), [])

    def test_no_linked_issue_is_refused(self):
        self.assertEqual(len(problems("default", [], [])), 1)

    def test_a_closed_linked_issue_is_refused(self):
        found = problems("default", [Issue(5, False)], [])
        self.assertEqual(found, ["Issue #5 is closed; link an open issue."])

    def test_an_unknown_profile_is_refused(self):
        self.assertEqual(len(problems("strict", [Issue(5, True)], [])), 1)


class SpecProfile(unittest.TestCase):
    def test_a_proposal_file_needs_its_issue_ready(self):
        files = ["proposals/0002-foundations.md"]
        self.assertEqual(problems("spec", [Issue(2, True, READY)], files), [])

    def test_a_proposal_file_without_its_issue_is_refused(self):
        found = problems("spec", [Issue(7, True, {"process"})], ["proposals/0002-foundations.md"])
        self.assertIn('Adds the file of proposal 0002 but is not linked to #2. Add "Closes #2".', found)

    def test_a_proposal_issue_not_yet_ready_is_refused(self):
        found = problems("spec", [Issue(2, True, {"proposal", "status: evaluating"})], ["proposals/0002-foundations.md"])
        self.assertEqual(len(found), 1)

    def test_other_pull_requests_need_a_process_defect_or_proposal_issue(self):
        for label in ("process", "spec defect", "proposal"):
            with self.subTest(label=label):
                self.assertEqual(problems("spec", [Issue(16, True, {label})], ["PROCESS.md"]), [])

    def test_other_pull_requests_with_an_unlabelled_issue_are_refused(self):
        self.assertEqual(len(problems("spec", [Issue(16, True)], ["PROCESS.md"])), 1)


class ImplementationProfile(unittest.TestCase):
    def test_an_accepted_implementation_issue_is_enough(self):
        self.assertEqual(problems("implementation", [Issue(2, True, {"implements-proposal"})], []), [])

    def test_an_implementation_still_waiting_for_its_spec_is_refused(self):
        issue = Issue(2, True, {"implements-proposal", "waiting for spec"})
        found = problems("implementation", [issue], [])
        self.assertEqual(found, ['Issue #2 is still "waiting for spec": its proposal is not accepted yet.'])

    def test_a_bug_issue_is_enough(self):
        self.assertEqual(problems("implementation", [Issue(9, True)], []), [])


if __name__ == "__main__":
    unittest.main()
