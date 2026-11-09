import json
import pathlib
import tarfile
import tempfile
import unittest

from lib.compatibility import (
    EXCLUDED,
    FAILED,
    NOT_RUN,
    PASSED,
    TableError,
    by_proposal,
    feature_path,
    implementation,
    load_repositories,
    manifest_name,
    outcome,
    proposal_title,
    report_exclusions,
    report_languages,
    report_results,
    row_results,
    row_slug,
    table_rows,
    tiers_claimed,
)
from lib.compatibility_page import row_page, summary_page
from lib.compatibility_source import Source
from lib.conformance import Scenario
from lib.github_api import GitHubError

STEPS = "cases/tier-1/0008-steps/outcomes.feature"
RESCUE = "cases/tier-1/0003-rescue-steps/rescue.feature"
LATER = "cases/tier-2/0200-later/later.feature"


def scenarios():
    return [
        Scenario(STEPS, "A step succeeds", {"@tier-1", "@proposal-0008"}),
        Scenario(STEPS, "A step changed by an amendment", {"@tier-1", "@proposal-0008", "@proposal-0098"}),
        Scenario(STEPS, "An asynchronous step", {"@tier-1", "@proposal-0008", "@capability-async"}),
        Scenario(RESCUE, "A rescue step skips", {"@tier-1", "@proposal-0003", "@rescue-skip"}),
        Scenario(RESCUE, "A rescue step runs", {"@tier-1", "@proposal-0003"}),
    ]


def manifest(**changes):
    return {"cases": "v0.1.0", "proposals": [3, 8, 98], "capabilities": ["sync"], "impossible": {}, **changes}


def element(name, *statuses, kind="scenario"):
    return {"type": kind, "name": name, "steps": [{"result": {"status": s}} for s in statuses]}


def cucumber(uri, *elements):
    return json.dumps([{"uri": uri, "elements": list(elements)}])


def exclusions(*entries):
    return json.dumps(list(entries))


SKIP = {
    "feature": RESCUE,
    "scenario": "A rescue step skips",
    "tag": "rescue-skip",
    "proof": {"test": "a rescue step cannot skip", "file": "tests/ui/skipping.rs"},
}


class RepositoriesTest(unittest.TestCase):
    def test_reads_the_repositories(self):
        text = '{"repositories": ["itinera-dev/itinera-rs", "itinera-dev/itinera-j"]}'
        self.assertEqual(load_repositories(text), ["itinera-dev/itinera-rs", "itinera-dev/itinera-j"])

    def test_refuses_a_list_that_is_not_one(self):
        for text in ("[]", '{"repositories": []}', '{"repositories": ["itinera-rs"]}', "{"):
            with self.subTest(text=text), self.assertRaises(TableError):
                load_repositories(text)

    def test_refuses_two_repositories_of_the_same_name(self):
        for text in ('{"repositories": ["a/b", "a/b"]}', '{"repositories": ["a/b", "c/b"]}'):
            with self.subTest(text=text), self.assertRaisesRegex(TableError, "same name"):
                load_repositories(text)


class ReportLanguagesTest(unittest.TestCase):
    def test_a_repository_holding_one_language(self):
        self.assertEqual(report_languages(["cucumber.json", "exclusions.json", "api.tar.gz"]), [""])

    def test_a_repository_holding_several(self):
        names = ["cucumber-kotlin.json", "exclusions-kotlin.json", "cucumber-java.json", "exclusions-java.json"]
        self.assertEqual(report_languages(names), ["java", "kotlin"])

    def test_a_release_without_reports(self):
        self.assertEqual(report_languages(["api.tar.gz"]), [])

    def test_plain_and_named_reports_are_an_error(self):
        with self.assertRaisesRegex(TableError, "both"):
            report_languages(["cucumber.json", "exclusions.json", "cucumber-java.json", "exclusions-java.json"])

    def test_a_report_without_its_exclusions_is_an_error(self):
        with self.assertRaisesRegex(TableError, "exclusions-java.json"):
            report_languages(["cucumber-java.json"])
        with self.assertRaisesRegex(TableError, "cucumber.json"):
            report_languages(["exclusions.json"])


class ManifestNameTest(unittest.TestCase):
    def test_a_language_reads_its_own_manifest(self):
        self.assertEqual(manifest_name("java", {"conformance-java.json", "conformance.json"}), "conformance-java.json")

    def test_a_language_falls_back_to_the_plain_manifest(self):
        self.assertEqual(manifest_name("kotlin", {"conformance-java.json", "conformance.json"}), "conformance.json")
        self.assertEqual(manifest_name("", {"conformance.json"}), "conformance.json")

    def test_a_missing_manifest_is_an_error(self):
        with self.assertRaisesRegex(TableError, "conformance-java.json or conformance.json"):
            manifest_name("java", {"README.md"})


class ReportResultsTest(unittest.TestCase):
    def test_reads_the_feature_from_every_runners_uri(self):
        for uri in (
            "home/runner/work/_temp/x/itinera-dev-conformance-af630b4/cases/tier-1/0008-steps/outcomes.feature",
            "../../_temp/x/itinera-dev-conformance-af630b4/cases/tier-1/0008-steps/outcomes.feature",
            "file:///home/runner/work/_temp/x/cases/tier-1/0008-steps/outcomes.feature",
            "C:\\work\\cases\\tier-1\\0008-steps\\outcomes.feature",
        ):
            with self.subTest(uri=uri):
                self.assertEqual(feature_path(uri), STEPS)

    def test_an_outline_passes_only_when_every_example_passed(self):
        text = cucumber(
            STEPS,
            element("Each outcome", "passed", "passed"),
            element("Each outcome", "passed", "failed"),
            element("Another", "passed"),
            element("Ignored", "failed", kind="background"),
        )
        self.assertEqual(report_results(text), {(STEPS, "Each outcome"): False, (STEPS, "Another"): True})

    def test_a_failing_hook_fails_the_scenario(self):
        failing = {**element("Hooked", "passed"), "after": [{"result": {"status": "failed"}}]}
        self.assertEqual(report_results(cucumber(STEPS, failing)), {(STEPS, "Hooked"): False})

    def test_skipped_and_undefined_steps_do_not_pass(self):
        text = cucumber(STEPS, element("Skipped", "passed", "skipped"), element("Undefined", "undefined"))
        self.assertEqual(set(report_results(text).values()), {False})

    def test_refuses_a_report_that_is_not_one(self):
        for text in ("{", "{}"):
            with self.subTest(text=text), self.assertRaises(TableError):
                report_results(text)


class OutcomeTest(unittest.TestCase):
    def test_each_status_and_its_reason(self):
        s = scenarios()
        results = {(STEPS, "A step succeeds"): True, (STEPS, "A step changed by an amendment"): False}
        excluded = {(RESCUE, "A rescue step skips"): SKIP}
        found = [outcome(x, manifest(), results, excluded) for x in s]
        self.assertEqual([o.status for o in found], [PASSED, FAILED, NOT_RUN, EXCLUDED, FAILED])
        self.assertEqual(found[1].reason, "It failed.")
        self.assertEqual(found[2].reason, "It needs async, which is not claimed.")
        self.assertEqual(found[3].reason, "@rescue-skip")
        self.assertEqual(found[3].proof["file"], "tests/ui/skipping.rs")
        self.assertEqual(found[4].reason, "It is missing from the report.")

    def test_a_scenario_of_a_proposal_not_listed_is_not_run(self):
        found = outcome(scenarios()[1], manifest(proposals=[3, 8]), {}, {})
        self.assertEqual((found.status, found.reason), (NOT_RUN, "Proposal 0098 is not listed in the manifest."))


class TiersTest(unittest.TestCase):
    def test_the_tiers_whose_proposals_are_all_listed(self):
        s = scenarios() + [Scenario(LATER, "Later", {"@tier-2", "@proposal-0200"})]
        self.assertEqual(tiers_claimed(s, manifest()), 1)
        self.assertEqual(tiers_claimed(s, manifest(proposals=[3, 8, 98, 200])), 2)
        self.assertEqual(tiers_claimed(s, manifest(proposals=[8])), 0)


class CountsTest(unittest.TestCase):
    def test_a_scenario_counts_under_every_proposal_it_carries(self):
        found = [outcome(x, manifest(), {}, {}) for x in scenarios()]
        counted = by_proposal(found)
        self.assertEqual(sorted(counted), [3, 8, 98])
        self.assertEqual(counted[8]["scenarios"], 3)
        self.assertEqual(counted[98]["scenarios"], 1)

    def test_a_row_counts_every_scenario_once(self):
        report = cucumber(
            STEPS, element("A step succeeds", "passed"), element("A step changed by an amendment", "passed")
        )
        report_rescue = json.loads(cucumber(RESCUE, element("A rescue step runs", "passed")))
        text = json.dumps(json.loads(report) + report_rescue)
        row = row_results(scenarios(), manifest(), text, exclusions(SKIP))
        self.assertEqual(row["totals"], {PASSED: 3, EXCLUDED: 1, NOT_RUN: 1, FAILED: 0, "scenarios": 5})
        self.assertEqual(row["proposals"]["0008"], {PASSED: 2, EXCLUDED: 0, NOT_RUN: 1, FAILED: 0, "scenarios": 3})
        self.assertEqual(row["tiers"], 1)
        self.assertEqual([e["scenario"] for e in row["not_passed"]], ["An asynchronous step", "A rescue step skips"])


class NamesTest(unittest.TestCase):
    def test_names_and_pages(self):
        self.assertEqual(implementation("itinera-dev/itinera-j", "java"), "itinera-j java")
        self.assertEqual(implementation("itinera-dev/itinera-rs", ""), "itinera-rs")
        self.assertEqual(row_slug("itinera-dev/itinera-j", "v0.1.0", "java"), "itinera-j-v0.1.0-java.html")
        self.assertEqual(row_slug("itinera-dev/itinera-rs", "v0.1.0", ""), "itinera-rs-v0.1.0.html")

    def test_proposal_title(self):
        self.assertEqual(proposal_title("# 0002: Foundations\n\n- Issue: #2\n"), "Foundations")
        self.assertEqual(proposal_title("no heading"), "")


class FakeSource:
    """Releases, files and reports held in memory, as GitHub would answer."""

    def __init__(self, releases, files, texts, assets):
        self._releases, self._files, self._texts, self._assets = releases, files, texts, assets

    def releases(self, repository):
        return self._releases[repository]

    def files(self, repository, tag):
        return self._files[(repository, tag)]

    def text(self, repository, path, tag):
        return self._texts[(repository, path, tag)]

    def asset(self, repository, asset):
        return self._assets[asset["id"]]

    def scenarios(self, cases):
        if cases != "v0.1.0":
            raise TableError(f"The cases at {cases} cannot be downloaded.")
        return scenarios()


def release(tag, published, *names, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "published_at": published,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"id": f"{tag}/{n}", "name": n} for n in names],
    }


class TableRowsTest(unittest.TestCase):
    def source(self):
        report = cucumber(STEPS, element("A step succeeds", "passed"))
        return FakeSource(
            releases={
                "o/one": [
                    release(
                        "v0.1.0-beta.1", "2026-10-01T00:00:00Z", "cucumber.json", "exclusions.json", prerelease=True
                    ),
                    release("v0.1.0", "2026-11-09T00:00:00Z", "cucumber.json", "exclusions.json"),
                    release("v0.2.0", "", "cucumber.json", "exclusions.json", draft=True),
                    release("v0.0.1", "2026-09-01T00:00:00Z", "notes.txt"),
                ],
                "o/two": [
                    release(
                        "v1.0.0",
                        "2026-11-01T00:00:00Z",
                        "cucumber-java.json",
                        "exclusions-java.json",
                        "cucumber-kotlin.json",
                        "exclusions-kotlin.json",
                    )
                ],
            },
            files={
                ("o/one", "v0.1.0"): {"conformance.json"},
                ("o/one", "v0.1.0-beta.1"): {"conformance.json"},
                ("o/two", "v1.0.0"): {"conformance-java.json", "conformance.json"},
            },
            texts={
                ("o/one", "conformance.json", "v0.1.0"): json.dumps(manifest()),
                ("o/one", "conformance.json", "v0.1.0-beta.1"): json.dumps(manifest(cases="v0.1.0-rc.1")),
                ("o/two", "conformance-java.json", "v1.0.0"): json.dumps(manifest()),
                ("o/two", "conformance.json", "v1.0.0"): json.dumps(manifest(capabilities=["sync", "async"])),
            },
            assets={
                **{f"{t}/cucumber.json": report for t in ("v0.1.0", "v0.1.0-beta.1")},
                **{f"{t}/exclusions.json": "[]" for t in ("v0.1.0", "v0.1.0-beta.1")},
                "v1.0.0/cucumber-java.json": report,
                "v1.0.0/exclusions-java.json": "[]",
                "v1.0.0/cucumber-kotlin.json": report,
                "v1.0.0/exclusions-kotlin.json": "[]",
            },
        )

    def test_every_release_newest_first_without_drafts(self):
        rows = table_rows(self.source(), ["o/one", "o/two"], "o/conformance")
        self.assertEqual(
            [(r["implementation"], r["tag"]) for r in rows],
            [
                ("one", "v0.1.0"),
                ("one", "v0.1.0-beta.1"),
                ("one", "v0.0.1"),
                ("two java", "v1.0.0"),
                ("two kotlin", "v1.0.0"),
            ],
        )
        self.assertEqual(rows[0]["page"], "one-v0.1.0.html")
        self.assertTrue(rows[1]["prerelease"])

    def test_each_language_reads_its_manifest(self):
        rows = table_rows(self.source(), ["o/two"], "o/conformance")
        self.assertEqual([r["manifest"] for r in rows], ["conformance-java.json", "conformance.json"])
        self.assertEqual(rows[1]["capabilities"], ["async", "sync"])

    def test_a_release_that_cannot_be_read_is_a_row_holding_the_error(self):
        rows = table_rows(self.source(), ["o/one"], "o/conformance")
        self.assertEqual(rows[1]["error"], "The cases at v0.1.0-rc.1 cannot be downloaded.")
        self.assertEqual(rows[2]["error"], "The release carries no conformance report.")
        self.assertNotIn("error", rows[0])


class PagesTest(unittest.TestCase):
    def rows(self):
        return table_rows(TableRowsTest().source(), ["o/one", "o/two"], "o/conformance")

    def test_the_summary_shows_the_latest_and_collapses_the_rest(self):
        html = summary_page(self.rows(), "2026-11-09 12:00 UTC")
        latest, earlier = html.split("<h2>Earlier releases</h2>")
        self.assertIn('<a href="one-v0.1.0.html">v0.1.0</a>', latest)
        self.assertNotIn("v0.1.0-beta.1", latest)
        self.assertIn("<summary>Earlier releases of one (2)</summary>", earlier)
        self.assertIn("v0.1.0-beta.1 (pre-release)", earlier)
        self.assertIn('class="error">Error: The release carries no conformance report.', earlier)
        self.assertNotIn("Earlier releases of two", html)

    def test_a_row_page_lists_what_did_not_pass_under_each_proposal(self):
        titles = {"0003": {"title": "Rescue <steps>", "path": "proposals/0003-rescue-steps.md"}}
        source = TableRowsTest().source()
        source._assets["v0.1.0/exclusions.json"] = exclusions(SKIP)
        row = table_rows(source, ["o/one"], "o/conformance")[0]
        html = row_page(row, titles, "https://github.com/o/spec", "2026-11-09 12:00 UTC")
        self.assertIn(
            '<a href="https://github.com/o/spec/blob/main/proposals/0003-rescue-steps.md">'
            "0003: Rescue &lt;steps&gt;</a>",
            html,
        )
        self.assertIn("<summary>0003: Rescue &lt;steps&gt;: 1 excluded with proof, 1 failed or missing</summary>", html)
        self.assertIn('<a href="https://github.com/o/one/blob/v0.1.0/tests/ui/skipping.rs">', html)
        self.assertIn("A rescue step runs, in tier-1/0003-rescue-steps/rescue.feature: Failed or missing.", html)
        self.assertIn("<summary>0098: 1 failed or missing</summary>", html)



class MalformedReportTest(unittest.TestCase):
    def test_reads_what_it_can_of_a_malformed_report(self):
        text = json.dumps(
            [
                {"uri": STEPS, "elements": None},
                {"uri": 5, "elements": []},
                "not a feature",
                {
                    "uri": STEPS,
                    "elements": [
                        "not an element",
                        {"name": 7, "steps": []},
                        {"name": "Null result", "steps": [{"result": None}]},
                        {"name": "Null steps", "steps": None, "before": ["x"]},
                    ],
                },
            ]
        )
        self.assertEqual(report_results(text), {(STEPS, "Null result"): False, (STEPS, "Null steps"): False})

    def test_a_proof_that_is_not_text_is_left_out(self):
        bad = {**SKIP, "proof": {"test": "a test", "file": 5}}
        found = report_exclusions(json.dumps([bad]))
        self.assertEqual(found[(bad["feature"], bad["scenario"])]["proof"], {})
        self.assertEqual(report_exclusions(json.dumps([SKIP]))[(SKIP["feature"], SKIP["scenario"])]["proof"],
                         SKIP["proof"])

    def test_the_last_cases_folder_of_a_uri_is_the_conformance_one(self):
        uri = "/home/runner/work/cases/cases/_temp/conf-abc/cases/tier-1/0008-steps/outcomes.feature"
        self.assertEqual(feature_path(uri), STEPS)
        self.assertIsNone(feature_path("/home/runner/cases/notes.feature"))


class OutlineTest(unittest.TestCase):
    def outline(self):
        return Scenario(STEPS, "A step with <outcome> ends <how>", {"@tier-1", "@proposal-0008"})

    def test_an_outline_named_with_placeholders_matches_every_example(self):
        results = {(STEPS, "A step with success ends well"): True, (STEPS, "A step with failure ends badly"): True}
        self.assertEqual(outcome(self.outline(), manifest(), results, {}).status, PASSED)
        results[(STEPS, "A step with skip ends <how>")] = False
        self.assertEqual(outcome(self.outline(), manifest(), results, {}).status, FAILED)

    def test_a_placeholder_may_be_filled_with_nothing(self):
        scenario = Scenario(STEPS, "Value <v> works", {"@tier-1", "@proposal-0008"})
        self.assertEqual(outcome(scenario, manifest(), {(STEPS, "Value  works"): True}, {}).status, PASSED)

    def test_an_outline_with_no_example_in_the_report_is_missing(self):
        results = {(STEPS, "Something else"): True}
        found = outcome(self.outline(), manifest(), results, {})
        self.assertEqual((found.status, found.reason), (FAILED, "It is missing from the report."))


class SlugTest(unittest.TestCase):
    def test_a_tag_a_file_name_or_an_address_could_misread_is_replaced(self):
        self.assertEqual(row_slug("o/one", "release/1.0+build#2?x", ""), "one-release-1.0-build-2-x.html")


class ReleaseErrorsTest(unittest.TestCase):
    def test_an_error_of_a_release_whose_languages_cannot_be_told_shows_under_each_language(self):
        source = TableRowsTest().source()
        source._releases["o/two"].append(
            release("v1.1.0", "2026-11-05T00:00:00Z", "cucumber.json", "exclusions.json", "cucumber-java.json",
                    "exclusions-java.json")
        )
        rows = table_rows(source, ["o/two"], "o/conformance")
        self.assertEqual(
            [(r["implementation"], r["tag"], "error" in r) for r in rows],
            [
                ("two java", "v1.1.0", True),
                ("two kotlin", "v1.1.0", True),
                ("two java", "v1.0.0", False),
                ("two kotlin", "v1.0.0", False),
            ],
        )
        self.assertIn("both a plain report", rows[0]["error"])

    def test_one_language_without_a_manifest_fails_alone(self):
        source = TableRowsTest().source()
        source._files[("o/two", "v1.0.0")] = {"conformance-java.json"}
        rows = table_rows(source, ["o/two"], "o/conformance")
        self.assertNotIn("error", rows[0])
        self.assertEqual(rows[1]["error"], "The repository has no conformance-kotlin.json or conformance.json at the "
                                           "release's tag.")


class RowPageTest(unittest.TestCase):
    def row(self, extra_scenarios=(), **manifest_changes):
        report = cucumber(STEPS, element("A step succeeds", "passed"), element("<b>Injected</b>", "failed"))
        held = scenarios() + list(extra_scenarios)

        class Source(FakeSource):
            def scenarios(self, cases):
                return held

        source = Source(
            releases={"o/one": [release("v1.0+b", "2026-11-09T00:00:00Z", "cucumber.json", "exclusions.json")]},
            files={("o/one", "v1.0+b"): {"conformance.json"}},
            texts={("o/one", "conformance.json", "v1.0+b"): json.dumps(manifest(**manifest_changes))},
            assets={"v1.0+b/cucumber.json": report, "v1.0+b/exclusions.json": "[]"},
        )
        return table_rows(source, ["o/one"], "o/conformance")[0]

    def test_report_contents_are_escaped_and_tags_quoted(self):
        injected = Scenario(STEPS, "<b>Injected</b>", {"@tier-1", "@proposal-0008"})
        html = row_page(self.row([injected]), {}, "https://github.com/o/spec", "today")
        self.assertIn(
            "&lt;b&gt;Injected&lt;/b&gt;, in tier-1/0008-steps/outcomes.feature: Failed or missing. It failed.", html
        )
        self.assertNotIn("<b>Injected", html)
        self.assertIn('href="https://github.com/o/one/releases/tag/v1.0%2Bb"', html)

    def test_a_scenario_not_run_says_why(self):
        html = row_page(self.row(), {}, "https://github.com/o/spec", "today")
        self.assertIn("An asynchronous step, in tier-1/0008-steps/outcomes.feature: Not run. It needs async, which is "
                      "not claimed.", html)

    def test_a_scenario_without_a_proposal_is_listed_on_its_own(self):
        bare = Scenario(STEPS, "A scenario without a proposal", {"@tier-1"})
        row = self.row([bare])
        self.assertEqual(row["totals"][FAILED] + row["totals"][NOT_RUN] > 0, True)
        html = row_page(row, {}, "https://github.com/o/spec", "today")
        self.assertIn("<summary>Scenarios without a proposal: 1</summary>", html)
        self.assertNotIn("Every scenario passed.", html)


class FakeGitHub:
    def __init__(self, fail_tarball: bool | str = False):
        self.calls = []
        self.fail_tarball = fail_tarball

    def get(self, path):
        self.calls.append(path)
        return [{"name": "conformance.json"}]

    def download(self, path, accept):
        self.calls.append(path)
        return b"\xff\xfe"

    def download_asset(self, repo, asset_id):
        self.calls.append(asset_id)
        return "café".encode("utf-8")

    def extract_repository(self, repo, ref, into):
        self.calls.append(ref)
        if self.fail_tarball == "corrupt":
            raise tarfile.ReadError("not a gzip file")
        if self.fail_tarball:
            raise GitHubError("404")
        root = pathlib.Path(into, "conformance-abc")
        root.joinpath("cases/tier-1/0008-steps").mkdir(parents=True)
        root.joinpath("cases/tier-1/0008-steps/a.feature").write_text(
            "@tier-1 @proposal-0008\nFeature: F\n  Scenario: S\n    Given x\n", encoding="utf-8"
        )
        return root


class SourceTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)

    def test_a_cases_tag_that_cannot_be_downloaded_is_tried_once_and_others_still_work(self):
        github = FakeGitHub(fail_tarball=True)
        source = Source(github, "o/conformance", self.work.name)
        for tag in ("v9", "v9", "v8"):
            with self.subTest(tag=tag), self.assertRaisesRegex(TableError, f"o/conformance@{tag} cannot"):
                source.scenarios(tag)
        self.assertEqual(github.calls, ["v9", "v8"])
        github.fail_tarball = False
        self.assertEqual([s.name for s in source.scenarios("v7")], ["S"])
        self.assertEqual([s.name for s in source.scenarios("v7")], ["S"])
        self.assertEqual(github.calls, ["v9", "v8", "v7"])

    def test_a_corrupt_cases_archive_is_an_error(self):
        source = Source(FakeGitHub(fail_tarball="corrupt"), "o/conformance", self.work.name)
        with self.assertRaisesRegex(TableError, "not a gzip file"):
            source.scenarios("v1")

    def test_tags_are_quoted_and_text_that_is_not_utf8_is_an_error(self):
        github = FakeGitHub()
        source = Source(github, "o/conformance", self.work.name)
        self.assertEqual(source.files("o/one", "v1.0+b"), {"conformance.json"})
        with self.assertRaisesRegex(TableError, "conformance.json is not UTF-8"):
            source.text("o/one", "conformance.json", "v1.0+b")
        self.assertEqual(source.asset("o/one", {"id": 3, "name": "cucumber.json"}), "café")
        self.assertEqual(
            github.calls[:2],
            ["/repos/o/one/contents?ref=v1.0%2Bb", "/repos/o/one/contents/conformance.json?ref=v1.0%2Bb"],
        )



if __name__ == "__main__":
    unittest.main()
