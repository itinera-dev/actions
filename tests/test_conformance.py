import json
import pathlib
import tempfile
import unittest

from lib.conformance import (
    ReportNames,
    Scenario,
    exclusion_problems,
    exclusions_report,
    language_problems,
    load_manifest,
    manifest_problems,
    parse_feature,
    read_scenarios,
    report_names,
    tag_expression,
)

FEATURE = '''\
@tier-1 @proposal-0012
Feature: The local executor
  Free text that mentions Scenario: and @proposal-0099 is not parsed.

  Background:
    Given a workflow "orders"

  Scenario: run returns the result
    Given a step that writes:
      """
      Scenario: inside a doc string
      @proposal-0098
      """
    Then the journey ends

  @capability-sync @proposal-0042 @mode-not-accepted  # an amendment
  Scenario: A synchronous-only executor refuses an asynchronous step
    Then it is refused

  @proposal-0041
  Rule: Hooks
    Scenario Outline: A hook reads <key>
      Then it reads "<key>"

      @capability-async
      Examples:
        | key |
        | a   |

    Example: A hook in a rule
      Then it runs
'''

PATH = "cases/tier-1/0012-local-executor/local-executor.feature"


def manifest(**changes):
    base = {"cases": "v0.1.0-rc.2", "proposals": [], "capabilities": ["sync", "async"], "impossible": {}}
    return {**base, **changes}


def entry(feature, scenario):
    return {"feature": feature, "scenario": scenario, "proof": {"test": "t", "file": "tests/proofs.rs"}}


class ScenarioApplies(unittest.TestCase):
    def test_a_scenario_needing_no_capability_applies_to_every_language(self):
        self.assertTrue(Scenario("cases/a.feature", "A", {"@proposal-0012"}).applies([]))

    def test_a_scenario_applies_when_every_capability_it_needs_is_claimed(self):
        scenario = Scenario("cases/a.feature", "A", {"@proposal-0009", "@capability-async", "@capability-testing"})
        self.assertTrue(scenario.applies(["sync", "async", "testing"]))

    def test_a_scenario_needing_a_capability_not_claimed_does_not_apply(self):
        scenario = Scenario("cases/a.feature", "A", {"@proposal-0009", "@capability-async", "@capability-testing"})
        self.assertFalse(scenario.applies(["async"]))


class ParseFeature(unittest.TestCase):
    def setUp(self):
        self.scenarios = {s.name: s for s in parse_feature(PATH, FEATURE)}

    def test_every_scenario_is_found_once(self):
        self.assertEqual(
            sorted(self.scenarios),
            [
                "A hook in a rule",
                "A hook reads <key>",
                "A synchronous-only executor refuses an asynchronous step",
                "run returns the result",
            ],
        )

    def test_a_scenario_inherits_its_feature_tags(self):
        self.assertEqual(self.scenarios["run returns the result"].tags, {"@tier-1", "@proposal-0012"})

    def test_scenario_tags_add_to_feature_tags_and_comments_are_ignored(self):
        tags = self.scenarios["A synchronous-only executor refuses an asynchronous step"].tags
        expected = {"@tier-1", "@proposal-0012", "@capability-sync", "@proposal-0042", "@mode-not-accepted"}
        self.assertEqual(tags, expected)

    def test_rule_and_examples_tags_reach_their_scenarios(self):
        self.assertEqual(
            self.scenarios["A hook reads <key>"].tags,
            {"@tier-1", "@proposal-0012", "@proposal-0041", "@capability-async"},
        )
        self.assertEqual(self.scenarios["A hook in a rule"].tags, {"@tier-1", "@proposal-0012", "@proposal-0041"})

    def test_a_scenario_knows_its_proposals(self):
        self.assertEqual(self.scenarios["A hook in a rule"].proposals(), {12, 41})

    def test_scenarios_carry_their_feature_path(self):
        self.assertEqual({s.feature for s in self.scenarios.values()}, {PATH})


class ReadScenarios(unittest.TestCase):
    def test_every_feature_under_cases_is_read_with_its_path_from_the_root(self):
        with tempfile.TemporaryDirectory() as work:
            root = pathlib.Path(work)
            folder = root / "cases/tier-1/0012-local-executor"
            folder.mkdir(parents=True)
            (folder / "local-executor.feature").write_text(FEATURE, encoding="utf-8")
            (root / "README.feature").write_text("Feature: not a case\n  Scenario: Outside\n", encoding="utf-8")
            self.assertEqual({s.feature for s in read_scenarios(root)}, {PATH})


class ManifestProblems(unittest.TestCase):
    def test_a_complete_manifest_has_none(self):
        impossible = {"non-value": [entry("cases/x.feature", "A closure")]}
        self.assertEqual(manifest_problems(manifest(proposals=[2, 8], impossible=impossible)), [])

    def test_missing_fields_are_reported(self):
        self.assertEqual(len(manifest_problems({})), 4)

    def test_proposals_must_be_numbers(self):
        self.assertEqual(len(manifest_problems(manifest(proposals=["0002"]))), 1)
        self.assertEqual(len(manifest_problems(manifest(proposals=[True]))), 1)

    def test_an_entry_needs_its_proof(self):
        impossible = {"non-value": [{"feature": "cases/x.feature", "scenario": "A closure"}]}
        self.assertEqual(len(manifest_problems(manifest(impossible=impossible))), 1)


class LoadManifest(unittest.TestCase):
    def test_a_complete_manifest_is_loaded_with_no_problem(self):
        loaded = manifest(proposals=[2])
        self.assertEqual(load_manifest("conformance.json", json.dumps(loaded)), (loaded, []))

    def test_a_manifest_that_does_not_parse_is_refused_in_its_name(self):
        loaded, found = load_manifest("conformance-java.json", "{")
        self.assertIsNone(loaded)
        self.assertRegex(found[0], "^conformance-java.json cannot be read")

    def test_a_manifest_that_is_not_an_object_is_refused_in_its_name(self):
        self.assertEqual(load_manifest("conformance.json", "[]"), (None, ["conformance.json must hold an object."]))

    def test_each_problem_of_a_manifests_shape_names_the_manifest(self):
        loaded, found = load_manifest("conformance-java.json", "{}")
        self.assertIsNone(loaded)
        self.assertEqual(len(found), 4)
        self.assertTrue(all(problem.startswith("conformance-java.json: ") for problem in found))


class ExclusionProblems(unittest.TestCase):
    scenarios = [
        Scenario("cases/a.feature", "Excluded", {"@proposal-0010", "@invalid-lifecycle"}),
        Scenario("cases/a.feature", "Ordinary", {"@proposal-0010"}),
    ]

    def test_every_excluded_scenario_with_an_entry_passes(self):
        impossible = {"invalid-lifecycle": [entry("cases/a.feature", "Excluded")]}
        self.assertEqual(exclusion_problems(self.scenarios, impossible), [])

    def test_a_tag_not_excluded_needs_no_entries(self):
        self.assertEqual(exclusion_problems(self.scenarios, {}), [])

    def test_an_excluded_scenario_without_an_entry_is_refused(self):
        found = exclusion_problems(self.scenarios, {"invalid-lifecycle": []})
        self.assertEqual(len(found), 1)
        self.assertIn("Excluded", found[0])

    def test_an_entry_naming_no_scenario_is_refused(self):
        impossible = {"invalid-lifecycle": [entry("cases/a.feature", "Excluded"), entry("cases/a.feature", "Gone")]}
        found = exclusion_problems(self.scenarios, impossible)
        self.assertEqual(len(found), 1)
        self.assertIn("does not exist", found[0])

    def test_an_entry_naming_a_scenario_without_the_tag_is_refused(self):
        impossible = {"invalid-lifecycle": [entry("cases/a.feature", "Excluded"), entry("cases/a.feature", "Ordinary")]}
        found = exclusion_problems(self.scenarios, impossible)
        self.assertEqual(len(found), 1)
        self.assertIn("does not carry", found[0])


class TagExpression(unittest.TestCase):
    scenarios = [
        Scenario("cases/a.feature", "Base", {"@proposal-0012"}),
        Scenario("cases/a.feature", "Amended", {"@proposal-0012", "@proposal-0042", "@capability-sync"}),
        Scenario("cases/b.feature", "Async", {"@proposal-0009", "@capability-async"}),
        Scenario("cases/b.feature", "Excluded", {"@proposal-0009", "@non-value"}),
    ]

    def test_scenarios_wait_for_every_proposal_they_carry(self):
        self.assertEqual(
            tag_expression(self.scenarios, [12], ["sync", "async"], {}),
            "(@proposal-0012) and not @proposal-0009 and not @proposal-0042",
        )

    def test_listing_the_amendment_runs_its_scenarios_with_the_rest(self):
        self.assertEqual(
            tag_expression(self.scenarios, [42, 12, 9], ["sync", "async"], {}),
            "(@proposal-0009 or @proposal-0012 or @proposal-0042)",
        )

    def test_capabilities_not_claimed_and_impossible_tags_are_left_out(self):
        self.assertEqual(
            tag_expression(self.scenarios, [9, 12, 42], ["sync"], {"non-value": []}),
            "(@proposal-0009 or @proposal-0012 or @proposal-0042) and not @capability-async and not @non-value",
        )


class ExclusionsReport(unittest.TestCase):
    def test_every_entry_is_reported_with_its_tag(self):
        impossible = {"non-value": [entry("cases/b.feature", "B")], "late-handle": [entry("cases/a.feature", "A")]}
        self.assertEqual(
            exclusions_report(impossible),
            [
                {**entry("cases/a.feature", "A"), "tag": "late-handle"},
                {**entry("cases/b.feature", "B"), "tag": "non-value"},
            ],
        )


class ReportNamesOfALanguage(unittest.TestCase):
    def test_a_repository_holding_one_language_keeps_the_plain_names(self):
        self.assertEqual(
            report_names(""),
            ReportNames("cucumber.json", "exclusions.json", "conformance-report"),
        )

    def test_each_language_of_a_repository_holding_several_names_its_own_report(self):
        self.assertEqual(
            report_names("java"),
            ReportNames("cucumber-java.json", "exclusions-java.json", "conformance-report-java"),
        )

    def test_no_language_is_accepted(self):
        self.assertEqual(language_problems(""), [])

    def test_a_language_written_in_lower_case_letters_digits_and_hyphens_is_accepted(self):
        for language in ["java", "kotlin-android", "c99"]:
            with self.subTest(language=language):
                self.assertEqual(language_problems(language), [])

    def test_a_language_that_cannot_name_a_file_is_refused_by_name(self):
        for language in ["Java", "java/kotlin", "../java", "-java", "9java", "java kotlin"]:
            with self.subTest(language=language):
                found = language_problems(language)
                self.assertEqual(len(found), 1)
                self.assertIn(f'"{language}"', found[0])


if __name__ == "__main__":
    unittest.main()
