import unittest

from lib.linking import Context, Issue, problems, referenced_numbers, spec_number

READY = {"proposal", "status: ready"}


class ReferencedNumbers(unittest.TestCase):
    def test_refs_and_ref_are_recognised_in_any_case(self):
        self.assertEqual(referenced_numbers("Refs #40\nref #41\nREFS: #42"), [40, 41, 42])

    def test_closing_keywords_and_other_text_are_not_references(self):
        self.assertEqual(referenced_numbers("Closes #40, see #41 and prefs #42"), [])


class SpecNumber(unittest.TestCase):
    def test_the_number_comes_from_the_title(self):
        self.assertEqual(spec_number("Implement spec#8 (Steps)"), 8)
        self.assertEqual(spec_number("Cases for spec#12 (The local executor)"), 12)

    def test_a_title_without_a_spec_number_has_none(self):
        self.assertIsNone(spec_number("Add the pull request checks"))


class DefaultProfile(unittest.TestCase):
    def test_closing_an_open_issue_is_enough(self):
        self.assertEqual(problems("default", [Issue(5, True)], [], []), [])

    def test_referring_to_an_open_issue_is_enough(self):
        self.assertEqual(problems("default", [], [Issue(5, True)], []), [])

    def test_no_linked_issue_is_refused(self):
        self.assertEqual(len(problems("default", [], [], [])), 1)

    def test_a_closed_issue_is_refused_whether_closed_or_referred_to(self):
        self.assertEqual(problems("default", [Issue(5, False)], [], []), ["Issue #5 is closed; link an open issue."])
        self.assertEqual(problems("default", [], [Issue(5, False)], []), ["Issue #5 is closed; link an open issue."])

    def test_an_unknown_profile_is_refused(self):
        self.assertEqual(len(problems("strict", [Issue(5, True)], [], [])), 1)


class SpecProfile(unittest.TestCase):
    FILES = ["proposals/0008-steps.md"]

    def test_a_proposal_file_needs_its_issue_ready_and_its_cases_merged(self):
        context = Context(cases_merged={8: True})
        self.assertEqual(problems("spec", [Issue(8, True, READY)], [], self.FILES, context), [])

    def test_a_proposal_file_whose_cases_are_not_merged_is_refused(self):
        found = problems("spec", [Issue(8, True, READY)], [], self.FILES, Context(cases_merged={8: False}))
        self.assertEqual(found, ['The conformance cases for proposal 0008 are not merged yet ("Cases for spec#8" is open).'])

    def test_a_proposal_file_without_a_conformance_issue_is_refused(self):
        found = problems("spec", [Issue(8, True, READY)], [], self.FILES, Context(cases_merged={8: None}))
        self.assertEqual(len(found), 1)

    def test_a_proposal_file_must_close_its_issue_not_only_refer_to_it(self):
        found = problems("spec", [], [Issue(8, True, READY)], self.FILES, Context(cases_merged={8: True}))
        self.assertIn('Adds the file of proposal 0008 but does not close #8. Add "Closes #8".', found)

    def test_a_proposal_issue_not_yet_ready_is_refused(self):
        issue = Issue(8, True, {"proposal", "status: evaluating"})
        self.assertEqual(len(problems("spec", [issue], [], self.FILES, Context(cases_merged={8: True}))), 1)

    def test_other_pull_requests_need_a_process_defect_or_proposal_issue(self):
        for label in ("process", "spec defect", "proposal"):
            with self.subTest(label=label):
                self.assertEqual(problems("spec", [], [Issue(16, True, {label})], ["PROCESS.md"]), [])

    def test_other_pull_requests_with_an_unlabelled_issue_are_refused(self):
        self.assertEqual(len(problems("spec", [Issue(16, True)], [], ["PROCESS.md"])), 1)


class ImplementationProfile(unittest.TestCase):
    STEPS = Issue(40, True, {"implements-proposal"}, "Implement spec#8 (Steps)")

    def test_a_contribution_referring_to_the_implementation_issue_is_enough(self):
        self.assertEqual(problems("implementation", [], [self.STEPS], []), [])

    def test_closing_the_implementation_issue_requires_switching_on_its_proposal(self):
        found = problems("implementation", [self.STEPS], [], [], Context(manifest_before={2}, manifest_after={2}))
        self.assertEqual(
            found, ["Closes #40, which implements spec#8, but does not add 8 to the proposals in conformance.json."]
        )

    def test_closing_it_while_switching_on_its_proposal_is_accepted(self):
        context = Context(manifest_before={2}, manifest_after={2, 8})
        self.assertEqual(problems("implementation", [self.STEPS], [], [], context), [])

    def test_switching_on_a_proposal_requires_closing_its_implementation_issue(self):
        found = problems("implementation", [], [self.STEPS], [], Context(manifest_after={8}))
        self.assertEqual(found, ["Adds 8 to the proposals in conformance.json but does not close its implementation issue."])

    def test_an_implementation_still_waiting_for_its_spec_is_refused(self):
        issue = Issue(40, True, {"implements-proposal", "waiting for spec"}, "Implement spec#8 (Steps)")
        found = problems("implementation", [], [issue], [])
        self.assertEqual(found, ['Issue #40 is still "waiting for spec": its proposal is not accepted yet.'])

    def test_a_bug_issue_is_enough(self):
        self.assertEqual(problems("implementation", [Issue(9, True)], [], []), [])


class ConformanceProfile(unittest.TestCase):
    CASES = Issue(8, True, {"implements-proposal", "waiting for spec"}, "Cases for spec#8 (Steps)")

    def test_cases_waiting_for_a_ready_spec_are_accepted(self):
        self.assertEqual(problems("conformance", [self.CASES], [], [], Context(spec_ready={8: True})), [])

    def test_cases_waiting_for_a_spec_not_yet_ready_are_refused(self):
        found = problems("conformance", [self.CASES], [], [], Context(spec_ready={8: False}))
        self.assertEqual(found, ['Issue #8 is "waiting for spec" and spec#8 is not ready yet.'])

    def test_other_issues_are_enough(self):
        self.assertEqual(problems("conformance", [Issue(5, True, {"process"}, "Case format")], [], []), [])


if __name__ == "__main__":
    unittest.main()
