import unittest

from lib import gherkin

FEATURE = '''\
# language: en
@tier-2 @proposal-0133
Feature: Before and after hooks
  Checks proposal 0133.

  A second paragraph.

  Background:
    Given a workflow "orders"

  # A comment between scenarios.
  @capability-sync
  Scenario: A before hook runs first
    Given a step that writes:
      """json
      {"a": 1}
      \\"\\"\\"
      """
    And the hooks:
      | hook   | lifecycle |
      | before | a \\| b    |
      | after  |           |
    * the workflow runs

  Rule: Hooks of a rule
    Some rule text.

    Background:
      Given the step policies "audit"

    Scenario Outline: An outline under a rule
      Then the journey <result>

      @capability-async
      Examples: Results
        | result    |
        | succeeded |
'''


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.feature = gherkin.parse(FEATURE)

    def test_feature(self):
        self.assertEqual(self.feature.name, "Before and after hooks")
        self.assertEqual(self.feature.tags, ["@tier-2", "@proposal-0133"])
        self.assertEqual(self.feature.description, "Checks proposal 0133.\n\nA second paragraph.")
        self.assertEqual([s.text for s in self.feature.background.steps], ['a workflow "orders"'])

    def test_scenario_steps_tables_and_doc_strings(self):
        scenario = self.feature.children[0]
        self.assertEqual((scenario.keyword, scenario.name), ("Scenario", "A before hook runs first"))
        self.assertEqual(scenario.tags, ["@capability-sync"])
        self.assertEqual([s.keyword for s in scenario.steps], ["Given", "And", "*"])
        doc = scenario.steps[0].doc_string
        self.assertEqual((doc.content, doc.media_type), ('{"a": 1}\n"""', "json"))
        self.assertEqual(scenario.steps[1].table, [["hook", "lifecycle"], ["before", "a | b"], ["after", ""]])

    def test_rule_with_background_and_outline(self):
        rule = self.feature.children[1]
        self.assertIsInstance(rule, gherkin.Rule)
        self.assertEqual((rule.name, rule.description), ("Hooks of a rule", "Some rule text."))
        self.assertEqual(rule.background.steps[0].text, 'the step policies "audit"')
        (outline,) = rule.scenarios
        self.assertEqual(outline.keyword, "Scenario Outline")
        (examples,) = outline.examples
        self.assertEqual((examples.name, examples.tags), ("Results", ["@capability-async"]))
        self.assertEqual(examples.table, [["result"], ["succeeded"]])

    def test_scenarios_and_inherited_tags(self):
        found = [(r.name if r else None, s.name) for r, s in self.feature.scenarios()]
        self.assertEqual(found, [(None, "A before hook runs first"), ("Hooks of a rule", "An outline under a rule")])
        rule, outline = list(self.feature.scenarios())[1]
        self.assertEqual(self.feature.tags_of(rule, outline), ["@tier-2", "@proposal-0133", "@capability-async"])

    def test_text_that_looks_like_keywords_inside_a_doc_string(self):
        feature = gherkin.parse(
            'Feature: F\n  Scenario: S\n    Given text:\n      """\n      Scenario: not one\n      @tag\n'
            '      | not | a table |\n      """\n'
        )
        (scenario,) = feature.children
        self.assertEqual(scenario.steps[0].doc_string.content, "Scenario: not one\n@tag\n| not | a table |")
        self.assertIsNone(scenario.steps[0].table)

    def test_a_tag_line_with_a_comment(self):
        self.assertEqual(gherkin.parse_tags("@a @b  # @c is a comment"), ["@a", "@b"])

    def test_no_feature(self):
        self.assertIsNone(gherkin.parse("# only a comment\n"))

    def test_row_escapes(self):
        self.assertEqual(gherkin.parse_row(r"| a\nb | c\\d | \x |"), ["a\nb", "c\\d", "\\x"])


if __name__ == "__main__":
    unittest.main()
