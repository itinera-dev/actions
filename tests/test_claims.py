import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from lib.claims import (
    Entry,
    GitHubSource,
    combine,
    corrections_problems,
    library_path_problems,
    library_paths,
    minor_of,
    minor_problems,
    releases_of,
    releases_problems,
    section_changed,
    summary,
    summary_markdown,
    version_key,
)
from lib.conformance import load_manifest, report_names
from lib.github_api import GitHubError

ACTION = pathlib.Path(__file__).resolve().parent.parent / "release-claims" / "main.py"


def load_action():
    spec = importlib.util.spec_from_file_location("release_claims_main", ACTION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Versions(unittest.TestCase):
    def test_a_pre_release_comes_before_its_version(self):
        self.assertLess(version_key("v0.1.0-rc.20"), version_key("v0.1.0"))
        self.assertLess(version_key("v0.1.0"), version_key("v0.1.1"))
        self.assertLess(version_key("v0.1.9"), version_key("v0.1.10"))

    def test_the_minor_version_of_a_tag(self):
        self.assertEqual(minor_of("v0.1.0-beta.7"), "0.1")
        self.assertEqual(minor_of("v1.12.3"), "1.12")

    def test_a_commit_has_no_version(self):
        self.assertIsNone(version_key("199f560be10dc50090c3f2e8bc6afbd26b65964e"))
        self.assertIsNone(minor_of("main"))


class ReleasesSection(unittest.TestCase):
    def test_a_manifest_without_the_section_has_no_claims(self):
        self.assertEqual(releases_of({"cases": "v0.1.1"}), {})

    def test_well_formed_claims_have_no_problems(self):
        self.assertEqual(releases_problems({"v0.1.0-beta.7": ["v0.1.0", "v0.1.1"], "v0.1.0": ["v0.1.1"]}), [])

    def test_the_section_must_be_an_object(self):
        self.assertEqual(len(releases_problems(["v0.1.0"])), 1)

    def test_a_release_named_by_a_commit_is_refused(self):
        found = releases_problems({"cc58934": ["v0.1.1"]})
        self.assertEqual(len(found), 1)
        self.assertIn("never commits", found[0])

    def test_a_conformance_commit_is_refused(self):
        found = releases_problems({"v0.1.0": ["199f560be10dc50090c3f2e8bc6afbd26b65964e"]})
        self.assertEqual(len(found), 1)
        self.assertIn("never commits", found[0])

    def test_a_release_candidate_of_the_cases_is_refused(self):
        self.assertEqual(len(releases_problems({"v0.1.0": ["v0.1.0-rc.20"]})), 1)

    def test_an_empty_list_is_refused(self):
        self.assertEqual(len(releases_problems({"v0.1.0": []})), 1)

    def test_a_list_of_something_else_is_refused(self):
        self.assertEqual(len(releases_problems({"v0.1.0": "v0.1.1"})), 1)
        self.assertEqual(len(releases_problems({"v0.1.0": [1]})), 1)

    def test_a_tag_listed_twice_is_refused(self):
        found = releases_problems({"v0.1.0": ["v0.1.1", "v0.1.1"]})
        self.assertEqual(found, ['"releases.v0.1.0" lists "v0.1.1" more than once.'])


class SectionChanged(unittest.TestCase):
    def test_adding_the_section_changes_it(self):
        self.assertTrue(section_changed({}, {"releases": {"v0.1.0": ["v0.1.1"]}}))

    def test_adding_a_tag_changes_it(self):
        before = {"releases": {"v0.1.0": ["v0.1.0"]}}
        self.assertTrue(section_changed(before, {"releases": {"v0.1.0": ["v0.1.0", "v0.1.1"]}}))

    def test_changing_something_else_leaves_it(self):
        releases = {"v0.1.0": ["v0.1.1"]}
        before = {"cases": "v0.1.0", "releases": releases}
        self.assertFalse(section_changed(before, {"cases": "v0.1.1", "releases": dict(releases)}))

    def test_no_section_before_or_after_leaves_it(self):
        self.assertFalse(section_changed({}, {"cases": "v0.1.1"}))


class MinorVersion(unittest.TestCase):
    def test_patches_of_the_claimed_minor_version_are_accepted(self):
        self.assertEqual(minor_problems("v0.1.0-beta.7", "v0.1.0-rc.20", ["v0.1.0", "v0.1.1"]), [])

    def test_a_tag_of_another_minor_version_is_refused(self):
        found = minor_problems("v0.1.0", "v0.1.0", ["v0.1.1", "v0.2.0"])
        self.assertEqual(
            found, ['"releases.v0.1.0" lists "v0.2.0", outside spec 0.1, the minor version the release claims.']
        )

    def test_a_release_pinning_a_commit_cannot_claim(self):
        found = minor_problems("v0.1.0", "10e35c4", ["v0.1.1"])
        self.assertEqual(len(found), 1)
        self.assertIn("cannot be told", found[0])


class CorrectionsWithoutCases(unittest.TestCase):
    def test_no_list_means_no_problem(self):
        self.assertEqual(corrections_problems("v0.1.0", "v0.1.0", "v0.1.1", None), [])

    def test_a_correction_in_the_claimed_patch_is_refused(self):
        found = corrections_problems("v0.1.0", "v0.1.0", "v0.1.2", json.dumps({"v0.1.2": [150]}))
        self.assertEqual(len(found), 1)
        self.assertIn("spec#150", found[0])

    def test_a_correction_in_an_earlier_patch_counts_too(self):
        found = corrections_problems("v0.1.0", "v0.1.0", "v0.1.3", json.dumps({"v0.1.2": [150], "v0.1.3": []}))
        self.assertEqual(len(found), 1)
        self.assertIn("v0.1.2", found[0])

    def test_a_correction_the_release_already_pinned_does_not_count(self):
        self.assertEqual(corrections_problems("v0.1.3", "v0.1.2", "v0.1.3", json.dumps({"v0.1.2": [150]})), [])

    def test_a_correction_after_the_claimed_patch_does_not_count(self):
        self.assertEqual(corrections_problems("v0.1.0", "v0.1.0", "v0.1.1", json.dumps({"v0.1.2": [150]})), [])

    def test_a_release_candidate_pin_comes_before_its_version(self):
        found = corrections_problems("v0.1.0-beta.7", "v0.1.0-rc.20", "v0.1.0", json.dumps({"v0.1.0": [99]}))
        self.assertEqual(len(found), 1)

    def test_a_malformed_list_is_a_problem(self):
        self.assertEqual(len(corrections_problems("v0.1.0", "v0.1.0", "v0.1.1", "{")), 1)
        self.assertEqual(len(corrections_problems("v0.1.0", "v0.1.0", "v0.1.1", json.dumps({"next": [1]}))), 1)
        self.assertEqual(len(corrections_problems("v0.1.0", "v0.1.0", "v0.1.1", json.dumps({"v0.1.1": "150"}))), 1)


class LibraryPaths(unittest.TestCase):
    def test_paths_are_separated_by_spaces_or_new_lines(self):
        paths = library_paths("crates/itinera \n crates/itinera-core/\n")
        self.assertEqual(paths, ["crates/itinera", "crates/itinera-core"])

    def test_no_path_is_a_problem(self):
        self.assertEqual(len(library_path_problems([])), 1)

    def test_paths_outside_the_repository_are_refused(self):
        self.assertEqual(len(library_path_problems(["../elsewhere", ".", "/etc"])), 3)
        self.assertEqual(library_path_problems(["itinera", "packages/itinera"]), [])


def write(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class Combine(unittest.TestCase):
    def setUp(self):
        self.work = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.main = self.work / "main"
        self.release = self.work / "release"
        write(self.main, {"lib/new.txt": "main's library", "lib/kept.txt": "main", "runner/run.txt": "main's runner"})
        write(self.release, {"lib/old.txt": "the release's library", "runner/run.txt": "the release's runner"})

    def test_the_library_is_the_release_s_and_the_rest_is_main_s(self):
        into = self.work / "combined"
        self.assertEqual(combine(self.main, self.release, ["lib"], into), [])
        self.assertEqual(sorted(p.name for p in (into / "lib").iterdir()), ["old.txt"])
        self.assertEqual((into / "runner/run.txt").read_text(), "main's runner")

    def test_a_single_file_can_be_taken_from_the_release(self):
        into = self.work / "combined"
        self.assertEqual(combine(self.main, self.release, ["runner/run.txt"], into), [])
        self.assertEqual((into / "runner/run.txt").read_text(), "the release's runner")

    def test_a_path_the_release_does_not_have_is_a_problem(self):
        found = combine(self.main, self.release, ["lib", "missing"], self.work / "combined")
        self.assertEqual(found, ['The release has no "missing", which "library" names.'])
        self.assertFalse((self.work / "combined").exists())


class Summary(unittest.TestCase):
    def test_the_summary_points_at_each_entry_s_report(self):
        entries = [Entry("v0.1.0", "v0.1.1", "aaa", "bbb", True)]
        written = summary("java", "conformance-java.json", "main", "ccc", entries, report_names("java"))
        self.assertEqual(written["runner"], {"ref": "main", "commit": "ccc"})
        self.assertEqual(
            written["entries"],
            [
                {
                    "release": "v0.1.0",
                    "release_commit": "aaa",
                    "cases": "v0.1.1",
                    "cases_commit": "bbb",
                    "passed": True,
                    "problems": [],
                    "cucumber": "v0.1.0/v0.1.1/cucumber-java.json",
                    "exclusions": "v0.1.0/v0.1.1/exclusions-java.json",
                }
            ],
        )

    def test_the_markdown_names_each_result(self):
        entries = [Entry("v0.1.0", "v0.1.1", "a" * 40, "b", False, ["it broke"])]
        text = summary_markdown("", "main", "c" * 40, entries)
        self.assertIn("v0.1.0 (at aaaaaaaaaaaa) fails the cases at v0.1.1.", text)
        self.assertIn("  - it broke", text)


class ManifestReaders(unittest.TestCase):
    """The readers that came before the section accept it and leave it alone, however it is written."""

    def test_the_conformance_run_and_the_release_gate_load_a_manifest_with_claims(self):
        for releases in ({"v0.1.0": ["v0.1.1"]}, "not even an object"):
            text = json.dumps(
                {"cases": "v0.1.1", "proposals": [2], "capabilities": [], "impossible": {}, "releases": releases}
            )
            loaded, found = load_manifest("conformance.json", text)
            self.assertEqual(found, [])
            self.assertEqual(loaded["proposals"], [2])


class Answers:
    """A stand-in for the GitHub client, answering paths with what it was given."""

    def __init__(self, answers):
        self.answers = answers

    def get(self, path):
        answer = self.answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def download(self, path, accept):
        return self.get(path)


class Source(unittest.TestCase):
    def test_a_lightweight_tag_names_its_commit(self):
        github = Answers({"/repos/o/r/git/ref/tags/v1": {"object": {"type": "commit", "sha": "abc"}}})
        self.assertEqual(GitHubSource(github).tag_commit("o/r", "v1"), "abc")

    def test_an_annotated_tag_is_followed_to_its_commit(self):
        github = Answers(
            {
                "/repos/o/r/git/ref/tags/v1": {"object": {"type": "tag", "sha": "t1"}},
                "/repos/o/r/git/tags/t1": {"object": {"type": "commit", "sha": "abc"}},
            }
        )
        self.assertEqual(GitHubSource(github).tag_commit("o/r", "v1"), "abc")

    def test_a_missing_tag_has_no_commit(self):
        github = Answers({"/repos/o/r/git/ref/tags/v9": GitHubError("GET x failed with 404: Not Found")})
        self.assertIsNone(GitHubSource(github).tag_commit("o/r", "v9"))

    def test_other_failures_are_not_hidden(self):
        github = Answers({"/repos/o/r/git/ref/tags/v1": GitHubError("GET x failed with 500: oops")})
        with self.assertRaises(GitHubError):
            GitHubSource(github).tag_commit("o/r", "v1")

    def test_a_missing_file_has_no_text(self):
        github = Answers({"/repos/o/r/contents/c.json?ref=abc": GitHubError("GET x failed with 404: Not Found")})
        self.assertIsNone(GitHubSource(github).file_at("o/r", "abc", "c.json"))

    def test_a_file_is_read_as_text(self):
        github = Answers({"/repos/o/r/contents/c.json?ref=abc": b"{}"})
        self.assertEqual(GitHubSource(github).file_at("o/r", "abc", "c.json"), "{}")


FEATURE = """\
@tier-1 @proposal-0002
Feature: Steps
  Scenario: A step runs
    Then it runs

  @proposal-0003
  Scenario: A later proposal
    Then it runs too
"""

# The runner stand-in: it says which library it was built with, writes a report and passes unless told to fail.
RUNNER = (
    'python3 -c "import os, pathlib; '
    "pathlib.Path(os.environ['ITINERA_CONFORMANCE_REPORT']).write_text("
    "'[]' if pathlib.Path('lib/version.txt').read_text() != 'broken' else '')\" "
    "&& test \"$(cat lib/version.txt)\" != broken && cat lib/version.txt >> \"$RUNS\" "
    "&& echo \" $ITINERA_CONFORMANCE_TAGS\" >> \"$RUNS\""
)


def manifest(**changes):
    return {"cases": "v0.1.0", "proposals": [2], "capabilities": [], "impossible": {}, **changes}


class FakeSource:
    """Repositories in directories: each (repository, tag or branch) is a tree of files."""

    def __init__(self, work, trees):
        self.work = work
        self.trees = trees
        self.extracted = []

    def tag_commit(self, repo, tag):
        return f"{repo}@{tag}" if (repo, tag) in self.trees else None

    def branch_commit(self, repo, branch):
        return f"{repo}@{branch}"

    def file_at(self, repo, ref, path):
        repo, tag = ref.split("@") if "@" in ref else (repo, ref)
        return self.trees.get((repo, tag), {}).get(path)

    def extract(self, repo, ref, into):
        self.extracted.append(ref)
        repo, tag = ref.split("@")
        root = pathlib.Path(into) / "root"
        write(root, self.trees[(repo, tag)])
        return root


class Check(unittest.TestCase):
    def setUp(self):
        self.work = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.head = self.work / "head"
        self.head.mkdir()
        cwd = os.getcwd()
        os.chdir(self.head)
        self.addCleanup(os.chdir, cwd)
        self.runs = self.work / "runs.txt"
        self.runs.write_text("")
        self.trees = {
            ("o/lang", "main"): {"conformance.json": json.dumps(manifest(cases="v0.1.1")), "lib/version.txt": "main"},
            ("o/lang", "v0.1.0"): {"conformance.json": json.dumps(manifest()), "lib/version.txt": "v0.1.0"},
            ("o/lang", "v0.0.9"): {"conformance.json": json.dumps(manifest(cases="v0.0.3")), "lib/version.txt": "x"},
            ("o/lang", "v0.1.0-broken"): {"conformance.json": json.dumps(manifest()), "lib/version.txt": "broken"},
            ("o/conformance", "v0.1.0"): {"cases/tier-1/steps.feature": FEATURE},
            ("o/conformance", "v0.1.1"): {"cases/tier-1/steps.feature": FEATURE},
            ("o/conformance", "v0.1.2"): {
                "cases/tier-1/steps.feature": FEATURE,
                "corrections-without-cases.json": json.dumps({"v0.1.2": [150]}),
            },
        }
        self.source = FakeSource(self.work, self.trees)

    def env(self, releases, **extra):
        (self.head / "conformance.json").write_text(json.dumps(manifest(cases="v0.1.1", releases=releases)))
        return {
            **os.environ,
            "REPO": "o/lang",
            "REPORT_DIR": str(self.work / "report"),
            "LIBRARY": "lib",
            "COMMAND": RUNNER,
            "RUNS": str(self.runs),
            "RUNNER_TEMP": str(self.work),
            "GITHUB_STEP_SUMMARY": str(self.work / "summary.md"),
            **extra,
        }

    def check(self, env):
        with mock.patch("sys.stdout"):
            load_action().check(env, self.source)

    def claims(self):
        return json.loads((self.work / "report" / "claims.json").read_text())

    def test_each_claim_runs_the_release_s_library_with_main_s_runner_and_the_tag_s_cases(self):
        self.check(self.env({"v0.1.0": ["v0.1.0", "v0.1.1"]}))
        self.assertEqual(self.runs.read_text().split("\n")[:2], ["v0.1.0 (@proposal-0002) and not @proposal-0003"] * 2)
        written = self.claims()
        self.assertEqual(written["runner"], {"ref": "main", "commit": "o/lang@main"})
        self.assertEqual([(e["release"], e["cases"], e["passed"]) for e in written["entries"]],
                         [("v0.1.0", "v0.1.0", True), ("v0.1.0", "v0.1.1", True)])
        self.assertTrue((self.work / "report/v0.1.0/v0.1.1/cucumber.json").is_file())
        self.assertTrue((self.work / "report/v0.1.0/v0.1.1/exclusions.json").is_file())
        self.assertIn("v0.1.0", (self.work / "summary.md").read_text())

    def test_a_claim_that_does_not_pass_fails_the_check_and_is_reported(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.1.0-broken": ["v0.1.1"]}))
        self.assertEqual([e["passed"] for e in self.claims()["entries"]], [False])

    def test_a_missing_release_tag_is_refused_before_anything_runs(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.1.0": ["v0.1.1"], "v0.1.7": ["v0.1.1"]}))
        self.assertEqual(self.runs.read_text(), "")

    def test_a_missing_conformance_tag_is_refused(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.1.0": ["v0.1.9"]}))
        self.assertEqual(self.runs.read_text(), "")

    def test_a_tag_outside_the_release_s_minor_version_is_refused(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.0.9": ["v0.1.1"]}))
        self.assertEqual(self.runs.read_text(), "")

    def test_a_patch_with_a_correction_without_cases_is_refused(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.1.0": ["v0.1.2"]}))
        self.assertEqual(self.runs.read_text(), "")

    def test_a_malformed_section_is_refused(self):
        with self.assertRaises(SystemExit):
            self.check(self.env({"v0.1.0": ["10e35c4"]}))

    def test_no_claims_checks_nothing(self):
        self.check(self.env({}))
        self.assertEqual(self.source.extracted, [])

    def test_a_pull_request_leaving_the_section_alone_checks_nothing(self):
        releases = {"v0.1.0": ["v0.1.1"]}
        self.trees[("o/lang", "base")] = {"conformance.json": json.dumps(manifest(releases=releases))}
        event = self.work / "event.json"
        event.write_text(json.dumps({"pull_request": {"base": {"sha": "o/lang@base"}}}))
        self.check(self.env(releases, GITHUB_EVENT_PATH=str(event)))
        self.assertEqual(self.source.extracted, [])

    def test_a_pull_request_changing_the_section_checks_every_claim(self):
        self.trees[("o/lang", "base")] = {"conformance.json": json.dumps(manifest())}
        event = self.work / "event.json"
        event.write_text(json.dumps({"pull_request": {"base": {"sha": "o/lang@base"}}}))
        self.check(self.env({"v0.1.0": ["v0.1.1"]}, GITHUB_EVENT_PATH=str(event)))
        self.assertEqual([e["passed"] for e in self.claims()["entries"]], [True])

    def test_the_runner_comes_from_the_branch_asked_for(self):
        self.trees[("o/lang", "next")] = self.trees[("o/lang", "main")]
        self.check(self.env({"v0.1.0": ["v0.1.1"]}, RUNNER_REF="next"))
        self.assertEqual(self.claims()["runner"]["ref"], "next")

    def test_main_s_impossible_list_applies(self):
        proof = {"test": "t", "file": "x"}
        impossible = {
            "never": [
                {"feature": "cases/tier-1/steps.feature", "scenario": "A step runs", "proof": proof}
            ]
        }
        self.trees[("o/lang", "main")]["conformance.json"] = json.dumps(manifest(impossible=impossible))
        never = FEATURE.replace("  Scenario: A step runs", "  @never\n  Scenario: A step runs")
        self.trees[("o/conformance", "v0.1.1")] = {"cases/tier-1/steps.feature": never}
        self.check(self.env({"v0.1.0": ["v0.1.1"]}))
        self.assertIn("not @never", self.runs.read_text())
        exclusions = json.loads((self.work / "report/v0.1.0/v0.1.1/exclusions.json").read_text())
        self.assertEqual([e["scenario"] for e in exclusions], ["A step runs"])


if __name__ == "__main__":
    sys.exit(unittest.main())
