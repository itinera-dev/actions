import unittest

from lib.conformance import Scenario
from lib.release import (
    asset_upload_url,
    cargo_version,
    changelog_section,
    compare_path,
    draft_release,
    existing_release,
    gradle_properties_version,
    is_prerelease,
    java_properties,
    manifest_encoding,
    manifest_version,
    on_branch,
    tag_problems,
    tier_problems,
    version_of_tag,
)

WORKSPACE = '''\
[workspace]
members = ["crates/*"]

[workspace.package]
version = "0.1.0-rc.1"
edition = "2024"
'''

PACKAGE = '''\
[package]
name = "itinera"
version = "0.2.0"
'''

CHANGELOG = '''\
# Changelog

## [Unreleased]

- Nothing yet.

## [0.1.0-rc.1] - 2026-10-11

The first release candidate.

### Added

- Everything.

## 0.0.1

- A placeholder.

[0.1.0-rc.1]: https://github.com/o/r/releases/tag/v0.1.0-rc.1
'''


class CargoVersion(unittest.TestCase):
    def test_a_workspace_declares_its_version_in_workspace_package(self):
        self.assertEqual(cargo_version(WORKSPACE), "0.1.0-rc.1")

    def test_a_single_package_declares_its_own(self):
        self.assertEqual(cargo_version(PACKAGE), "0.2.0")

    def test_a_manifest_without_a_version_declares_none(self):
        self.assertIsNone(cargo_version('[workspace]\nmembers = ["a"]\n'))


GRADLE_PROPERTIES = '''\
group=org.itinera-dev
version=0.1.0-beta.1
org.gradle.caching=true
'''


class GradlePropertiesVersion(unittest.TestCase):
    def test_a_gradle_build_declares_its_version_under_the_key_version(self):
        self.assertEqual(gradle_properties_version(GRADLE_PROPERTIES), "0.1.0-beta.1")

    def test_a_gradle_properties_without_a_version_declares_none(self):
        self.assertIsNone(gradle_properties_version("group=org.itinera-dev\n"))


class JavaProperties(unittest.TestCase):
    def test_comments_and_blank_lines_hold_no_entries(self):
        self.assertEqual(java_properties("# version=1\n  ! version=2\n\n   \n"), {})

    def test_a_key_ends_at_an_equals_sign_a_colon_or_white_space(self):
        text = "a=1\nb:2\nc 3\nd = 4\ne\t:\t5\n"
        self.assertEqual(java_properties(text), {"a": "1", "b": "2", "c": "3", "d": "4", "e": "5"})

    def test_a_key_alone_has_an_empty_value(self):
        self.assertEqual(java_properties("version\n"), {"version": ""})

    def test_a_line_ending_in_a_backslash_goes_on_in_the_next_without_its_leading_space(self):
        self.assertEqual(java_properties("version=0.1.\\\n    0\n"), {"version": "0.1.0"})

    def test_a_line_ending_in_an_escaped_backslash_does_not_go_on(self):
        self.assertEqual(java_properties("a=b\\\\\nversion=1\n"), {"a": "b\\", "version": "1"})

    def test_escapes_are_read_in_keys_and_values(self):
        text = "the\\ version\\=x=0\\u002e1\\t\\:\n"
        self.assertEqual(java_properties(text), {"the version=x": "0.1\t:"})

    def test_a_comment_ending_in_a_backslash_does_not_go_on(self):
        self.assertEqual(java_properties("# a comment\\\nversion=1\n"), {"version": "1"})

    def test_a_continuation_that_leaves_the_entry_empty_lets_a_comment_follow(self):
        self.assertEqual(java_properties("\\\n#version=1\n"), {})

    def test_a_carriage_return_ends_a_line_alone_or_before_a_line_feed(self):
        self.assertEqual(java_properties("a=1\rversion=2\r\nb=3"), {"a": "1", "version": "2", "b": "3"})

    def test_only_a_line_feed_or_a_carriage_return_ends_a_line(self):
        self.assertEqual(java_properties("a=b\fversion=9\u2028c\n"), {"a": "b\fversion=9\u2028c"})

    def test_a_form_feed_is_white_space_around_a_key(self):
        self.assertEqual(java_properties("\fversion\f=\f1\n"), {"version": "1"})

    def test_only_the_first_separator_is_skipped(self):
        self.assertEqual(java_properties("a = =b\n"), {"a": "=b"})

    def test_a_value_keeps_its_trailing_white_space(self):
        self.assertEqual(java_properties("version=1 \t\n"), {"version": "1 \t"})

    def test_a_later_entry_replaces_an_earlier_one(self):
        self.assertEqual(java_properties("version=1\nversion=2\n"), {"version": "2"})

    def test_a_malformed_unicode_escape_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not a Unicode escape"):
            java_properties("version=\\u12\n")


class ManifestEncoding(unittest.TestCase):
    def test_a_gradle_properties_is_read_as_iso_8859_1_as_gradle_reads_it(self):
        self.assertEqual(manifest_encoding("sub/gradle.properties"), "latin-1")

    def test_other_manifests_are_read_as_utf_8(self):
        self.assertEqual(manifest_encoding("packages/itinera/package.json"), "utf-8")


class ManifestVersion(unittest.TestCase):
    def test_a_package_json_declares_its_version(self):
        manifest = '{"name": "itinera", "version": "0.1.0-beta.1"}'
        self.assertEqual(manifest_version("packages/itinera/package.json", manifest), "0.1.0-beta.1")

    def test_a_package_json_that_does_not_parse_is_refused(self):
        with self.assertRaisesRegex(ValueError, "^package.json cannot be parsed"):
            manifest_version("package.json", "{")

    def test_the_reader_is_chosen_by_file_name(self):
        self.assertEqual(manifest_version("crates/itinera/Cargo.toml", PACKAGE), "0.2.0")

    def test_a_gradle_properties_is_read_for_its_version(self):
        self.assertEqual(manifest_version("gradle.properties", GRADLE_PROPERTIES), "0.1.0-beta.1")

    def test_a_gradle_properties_with_a_malformed_escape_is_refused(self):
        with self.assertRaisesRegex(ValueError, "^gradle.properties cannot be parsed"):
            manifest_version("gradle.properties", "version=\\u0\n")

    def test_an_unknown_manifest_is_refused(self):
        with self.assertRaisesRegex(ValueError, "reads Cargo.toml, gradle.properties, package.json"):
            manifest_version("pom.xml", "<project/>")

    def test_a_manifest_that_does_not_parse_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot be parsed"):
            manifest_version("Cargo.toml", "[package\n")

    def test_a_manifest_without_a_version_is_refused(self):
        with self.assertRaisesRegex(ValueError, "declares no version"):
            manifest_version("Cargo.toml", "[workspace]\n")


class TagProblems(unittest.TestCase):
    def test_v_followed_by_the_version_may_be_released(self):
        self.assertEqual(tag_problems("tag", "v0.1.0-rc.1", "0.1.0-rc.1"), [])

    def test_a_tag_naming_another_version_is_refused(self):
        found = tag_problems("tag", "v0.1.0-rc1", "0.1.0-rc.1")
        self.assertEqual(len(found), 1)
        self.assertIn('"v0.1.0-rc.1"', found[0])

    def test_a_tag_without_its_v_is_refused(self):
        self.assertEqual(len(tag_problems("tag", "0.1.0-rc.1", "0.1.0-rc.1")), 1)

    def test_a_branch_cannot_request_a_release(self):
        found = tag_problems("branch", "v0.1.0-rc.1", "0.1.0-rc.1")
        self.assertEqual(len(found), 1)
        self.assertIn("not a branch", found[0])


class ComparePath(unittest.TestCase):
    def test_the_comparison_runs_from_the_commit_to_the_branch(self):
        self.assertEqual(compare_path("o/r", "abc123", "main"), "/repos/o/r/compare/abc123...main?per_page=1")


class OnBranch(unittest.TestCase):
    def test_a_commit_the_branch_contains_is_on_it(self):
        self.assertTrue(on_branch("ahead"))
        self.assertTrue(on_branch("identical"))

    def test_a_commit_the_branch_does_not_contain_is_not_on_it(self):
        self.assertFalse(on_branch("behind"))
        self.assertFalse(on_branch("diverged"))


class TierProblems(unittest.TestCase):
    scenarios = [
        Scenario("cases/tier-1/0002-foundations/a.feature", "A", {"@proposal-0002"}),
        Scenario("cases/tier-1/0012-local-executor/b.feature", "B", {"@proposal-0012", "@proposal-0042"}),
        Scenario("cases/tier-2/0100-transfers/c.feature", "C", {"@proposal-0100"}),
    ]
    conversions = [
        Scenario("cases/tier-1/0054-failures/d.feature", "D", {"@proposal-0113", "@capability-value-conversions"}),
        Scenario("cases/tier-1/0054-failures/e.feature", "E", {"@proposal-0113", "@capability-value-conversions"}),
    ]

    def test_listing_every_proposal_of_the_tier_claims_it(self):
        self.assertEqual(tier_problems(self.scenarios[:2], [2, 12, 42], [], 1, "conformance.json"), [])

    def test_a_proposal_of_the_tier_not_listed_is_refused(self):
        found = tier_problems(self.scenarios, [2, 12], [], 1, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("0042", found[0])

    def test_a_proposal_not_listed_is_refused_in_the_name_of_the_manifest_that_misses_it(self):
        found = tier_problems(self.scenarios[:2], [2, 12], [], 1, "conformance-java.json")
        self.assertEqual(found, ["Proposal 0042, of tier 1 or below, is not listed in conformance-java.json."])

    def test_claiming_a_tier_needs_every_tier_below_it(self):
        found = tier_problems(self.scenarios, [100], [], 2, "conformance.json")
        self.assertEqual(len(found), 3)

    def test_proposals_of_higher_tiers_are_not_required(self):
        self.assertEqual(tier_problems(self.scenarios, [2, 12, 42], [], 1, "conformance.json"), [])

    def test_scenarios_outside_a_tier_folder_are_not_required(self):
        scenarios = [*self.scenarios[:2], Scenario("cases/drafts/x.feature", "X", {"@proposal-0099"})]
        self.assertEqual(tier_problems(scenarios, [2, 12, 42], [], 1, "conformance.json"), [])

    def test_a_proposal_whose_every_case_needs_a_capability_not_claimed_is_not_required(self):
        scenarios = [*self.scenarios, *self.conversions]
        self.assertEqual(tier_problems(scenarios, [2, 12, 42], ["sync"], 1, "conformance.json"), [])

    def test_a_proposal_whose_capability_is_claimed_is_required(self):
        scenarios = [*self.scenarios, *self.conversions]
        found = tier_problems(scenarios, [2, 12, 42], ["value-conversions"], 1, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("0113", found[0])

    def test_a_proposal_with_one_case_needing_no_capability_left_unclaimed_is_required(self):
        scenarios = [*self.conversions, Scenario("cases/tier-1/0054-failures/f.feature", "F", {"@proposal-0113"})]
        found = tier_problems(scenarios, [], ["sync"], 1, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("0113", found[0])

    def test_an_amended_proposal_with_cases_of_its_own_is_required_without_its_amendments_capability(self):
        scenarios = [*self.conversions, Scenario("cases/tier-1/0054-failures/g.feature", "G", {"@proposal-0054"})]
        scenarios[0] = Scenario(scenarios[0].feature, "D", {*scenarios[0].tags, "@proposal-0054"})
        found = tier_problems(scenarios, [], ["sync"], 1, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("0054", found[0])

    def test_a_tier_below_1_cannot_be_claimed(self):
        found = tier_problems(self.scenarios, [2, 12, 42], [], 0, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("1 or more", found[0])

    def test_a_tier_without_cases_cannot_be_claimed(self):
        found = tier_problems(self.scenarios[2:], [100], [], 1, "conformance.json")
        self.assertEqual(len(found), 1)
        self.assertIn("no proposal", found[0])


class Prerelease(unittest.TestCase):
    def test_a_release_candidate_is_a_prerelease(self):
        self.assertTrue(is_prerelease("0.1.0-rc.1"))

    def test_a_plain_version_is_not(self):
        self.assertFalse(is_prerelease("0.1.0"))

    def test_build_metadata_alone_is_not(self):
        self.assertFalse(is_prerelease("0.1.0+build-5"))


class ChangelogSection(unittest.TestCase):
    def test_the_section_runs_to_the_next_version_heading(self):
        self.assertEqual(
            changelog_section(CHANGELOG, "0.1.0-rc.1"),
            "The first release candidate.\n\n### Added\n\n- Everything.",
        )

    def test_the_last_section_stops_at_the_link_definitions(self):
        self.assertEqual(changelog_section(CHANGELOG, "0.0.1"), "- A placeholder.")

    def test_headings_in_other_common_styles_are_found(self):
        for heading in ("## 0.2.0", "## v0.2.0", "##\t0.2.0", "## [0.2.0](https://x/compare/a...b) (2026-10-11)"):
            with self.subTest(heading=heading):
                self.assertEqual(changelog_section(f"{heading}\n\nNotes.\n", "0.2.0"), "Notes.")

    def test_an_empty_section_has_no_notes(self):
        self.assertIsNone(changelog_section("## [0.2.0]\n\n## [0.1.0]\n\nNotes.\n", "0.2.0"))

    def test_a_version_without_a_section_has_none(self):
        self.assertIsNone(changelog_section(CHANGELOG, "0.1.0"))

    def test_a_version_named_only_in_a_lower_heading_has_none(self):
        self.assertIsNone(changelog_section("# Changelog\n\n### 0.1.0\n", "0.1.0"))


class DraftRelease(unittest.TestCase):
    def test_a_release_candidate_is_drafted_as_a_prerelease_named_after_its_tag(self):
        self.assertEqual(
            draft_release("v0.1.0-rc.1", "Notes."),
            {"tag_name": "v0.1.0-rc.1", "name": "v0.1.0-rc.1", "body": "Notes.", "draft": True, "prerelease": True},
        )

    def test_a_plain_version_is_drafted_as_a_release(self):
        self.assertFalse(draft_release("v0.1.0", "Notes.")["prerelease"])

    def test_the_version_of_a_tag_drops_its_v(self):
        self.assertEqual(version_of_tag("v0.1.0-rc.1"), "0.1.0-rc.1")


class ExistingRelease(unittest.TestCase):
    releases = [{"tag_name": "v0.1.0", "draft": False}, {"tag_name": "v0.2.0-rc.1", "draft": True}]

    def test_a_release_of_the_tag_is_found_whether_draft_or_published(self):
        self.assertEqual(existing_release(self.releases, "v0.2.0-rc.1"), self.releases[1])
        self.assertEqual(existing_release(self.releases, "v0.1.0"), self.releases[0])

    def test_a_tag_without_a_release_has_none(self):
        self.assertIsNone(existing_release(self.releases, "v0.3.0"))


class AssetUploadUrl(unittest.TestCase):
    def test_the_template_is_replaced_by_the_assets_name(self):
        release = {"upload_url": "https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}"}
        self.assertEqual(
            asset_upload_url(release, "cucumber.json"),
            "https://uploads.github.com/repos/o/r/releases/1/assets?name=cucumber.json",
        )


if __name__ == "__main__":
    unittest.main()
