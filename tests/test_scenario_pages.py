import pathlib
import re
import tempfile
import unittest

from lib import gherkin
from lib import scenario_pages as sp

FEATURE = '''\
@tier-1 @proposal-0003
Feature: Rescuing a step
  Checks proposal 0003.

  Scenario: The rescue step's contributions reach the step
    Given a workflow "orders" with the steps:
      | step   | rescue |
      | charge | yes    |
    Then the journey succeeded

  @capability-sync
  Scenario: The rescue steps contributions reach the step
    Given a workflow "<orders>"

  Rule: A rule
    Scenario: Background
      Given a workflow "orders"
'''


def write_cases(root, files):
    for path, text in files.items():
        target = pathlib.Path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


class AnchorTest(unittest.TestCase):
    def test_anchor(self):
        self.assertEqual(
            sp.anchor("The rescue step's contributions reach the step's second attempt"),
            "the-rescue-steps-contributions-reach-the-steps-second-attempt",
        )
        self.assertEqual(sp.anchor("  FailWorkflow, then (twice): done!  "), "failworkflow-then-twice-done")
        self.assertEqual(sp.anchor("!!!"), "scenario")

    def test_repeated_anchors_take_a_number_in_file_order(self):
        path = "cases/tier-1/0003-rescue-steps/rescuing.feature"
        file = sp.assign_anchors(sp.FeatureFile(path, gherkin.parse(FEATURE)))
        anchors = [file.anchors[id(s)] for _, s in file.feature.scenarios()]
        self.assertEqual(
            anchors,
            [
                "the-rescue-steps-contributions-reach-the-step",
                "the-rescue-steps-contributions-reach-the-step-2",
                "background-2",
            ],
        )
        self.assertEqual(file.anchors[id(file.feature.children[2])], "rule-a-rule")


class VersionTest(unittest.TestCase):
    def test_order(self):
        names = ["v0.1.0-rc.2", "v0.1.0", "v0.1.0-rc.10", "v0.2.0", "v0.1.1", "other", "v0.1.0-rc.1"]
        self.assertEqual(
            sorted(names, key=sp.version_key),
            ["v0.2.0", "v0.1.1", "v0.1.0", "v0.1.0-rc.10", "v0.1.0-rc.2", "v0.1.0-rc.1", "other"],
        )

    def test_usable_ref(self):
        self.assertIsNone(sp.usable_ref("v0.1.0-rc.20"))
        self.assertIsNone(sp.usable_ref("main"))
        self.assertIsNotNone(sp.usable_ref("feature/x"))
        self.assertIsNotNone(sp.usable_ref(".."))
        self.assertIsNotNone(sp.usable_ref("index.html"))


class SiteTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.work.name, "repo")
        write_cases(
            root,
            {
                "cases/tier-1/0003-rescue-steps/rescuing.feature": FEATURE,
                "cases/tier-1/0002-foundations/listing.feature": "@tier-1 @proposal-0002\nFeature: Listing\n"
                "  Scenario: A listing\n    Then it lists\n",
                "cases/notes.txt": "not a feature",
                "cases/tier-1/empty.feature": "# nothing here\n",
            },
        )
        files = sp.read_features(root)
        self.site = pathlib.Path(self.work.name, "site")
        self.versions = [
            sp.Version("v0.1.0-rc.1", files),
            sp.Version("main", files, branch=True),
            sp.Version("v0.1.0", files),
        ]
        sp.write_site("itinera-dev/conformance", self.versions, self.site, build="7.1")

    def tearDown(self):
        self.work.cleanup()

    def read(self, path):
        return self.site.joinpath(path).read_text(encoding="utf-8")

    def test_files(self):
        written = sorted(p.relative_to(self.site).as_posix() for p in self.site.rglob("*") if p.is_file())
        expected_version = [
            "index.html",
            "tags/capability-sync.html",
            "tags/index.html",
            "tags/proposal-0002.html",
            "tags/proposal-0003.html",
            "tags/tier-1.html",
            "tier-1/0002-foundations/listing.html",
            "tier-1/0003-rescue-steps/rescuing.html",
        ]
        expected = ["cases/build.txt", "cases/index.html", "cases/style.css", "index.html"] + [
            f"cases/{v}/{p}" for v in ("main", "v0.1.0", "v0.1.0-rc.1") for p in expected_version
        ]
        self.assertEqual(written, sorted(expected))
        self.assertEqual(self.read("cases/build.txt"), "7.1\n")

    def test_feature_page(self):
        text = self.read("cases/v0.1.0/tier-1/0003-rescue-steps/rescuing.html")
        self.assertIn("<h1>Feature: Rescuing a step</h1>", text)
        self.assertIn(
            '<h2 id="the-rescue-steps-contributions-reach-the-step">'
            "Scenario: The rescue step&#x27;s contributions reach the step</h2>",
            text,
        )
        self.assertIn('<h2 id="rule-a-rule">Rule: A rule</h2>', text)
        self.assertIn('<h3 id="background-2">Scenario: Background</h3>', text)
        self.assertIn('<th scope="col">step</th><th scope="col">rescue</th>', text)
        self.assertIn("<td>charge</td><td>yes</td>", text)
        self.assertIn('<span class="keyword">Given</span> a workflow &quot;&lt;orders&gt;&quot;', text)
        self.assertIn('<a href="../../tags/capability-sync.html">@capability-sync</a>', text)
        self.assertIn(
            "https://github.com/itinera-dev/conformance/blob/v0.1.0/cases/tier-1/0003-rescue-steps/rescuing.feature",
            text,
        )
        self.assertIn('<link rel="stylesheet" href="../../../../cases/style.css">', text)
        self.assertNotIn("<script", text)
        self.assertNotIn("not a released version", text)

    def test_branch_pages_say_so(self):
        self.assertIn("not a released version", self.read("cases/main/tier-1/0002-foundations/listing.html"))
        self.assertIn("not a released version", self.read("cases/main/index.html"))

    def test_tag_page_lists_inherited_tags(self):
        text = self.read("cases/v0.1.0/tags/proposal-0003.html")
        self.assertIn("3 scenarios carry this tag.", text)
        self.assertIn(
            '<a href="../tier-1/0003-rescue-steps/rescuing.html#the-rescue-steps-contributions-reach-the-step-2">',
            text,
        )
        self.assertIn("1 scenario carries this tag.", self.read("cases/v0.1.0/tags/capability-sync.html"))
        index = self.read("cases/v0.1.0/tags/index.html")
        self.assertIn('<td><a href="tier-1.html">@tier-1</a></td><td>4</td>', index)

    def test_version_index_groups_by_tier_and_proposal(self):
        text = self.read("cases/v0.1.0/index.html")
        self.assertIn("2 features, 4 scenarios.", text)
        self.assertLess(text.index("<h3>0002-foundations</h3>"), text.index("<h3>0003-rescue-steps</h3>"))
        self.assertIn("<h2>Tier 1</h2>", text)

    def test_versions_list(self):
        text = self.read("cases/index.html")
        self.assertLess(text.index("main/index.html"), text.index("v0.1.0/index.html"))
        details = text.index("<details>")
        self.assertLess(text.index("v0.1.0/index.html"), details)
        self.assertGreater(text.index("v0.1.0-rc.1/index.html"), details)

    def test_every_link_resolves(self):
        ids = {p: set(re.findall(r'id="([^"]+)"', p.read_text(encoding="utf-8"))) for p in self.site.rglob("*.html")}
        for page in ids:
            for href in re.findall(r'href="([^"]+)"', page.read_text(encoding="utf-8")):
                if href.startswith("https://"):
                    continue
                path, _, fragment = href.partition("#")
                target = (page.parent / path).resolve() if path else page
                self.assertTrue(target.is_file(), f"{page}: {href}")
                if fragment:
                    self.assertIn(fragment, ids[target], f"{page}: {href}")

    def test_an_existing_root_index_is_kept(self):
        site = pathlib.Path(self.work.name, "with-table")
        site.mkdir()
        site.joinpath("index.html").write_text("table", encoding="utf-8")
        sp.write_site("itinera-dev/conformance", self.versions, site)
        self.assertEqual(site.joinpath("index.html").read_text(encoding="utf-8"), "table")


if __name__ == "__main__":
    unittest.main()
