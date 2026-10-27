import io
import pathlib
import tarfile
import tempfile
import unittest

from lib.reference import build_site, editions, overlap, precedence, version_of_release, waiting_page


def release(tag, *assets, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": name, "id": n} for n, name in enumerate(assets)],
    }


def archive(files):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, text in files.items():
            content = text.encode()
            info = tarfile.TarInfo(f"./{name}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return data.getvalue()


class VersionOfRelease(unittest.TestCase):
    def test_a_tag_of_v_and_a_semantic_version_names_it(self):
        self.assertEqual(version_of_release(release("v0.1.0-beta.4")), "0.1.0-beta.4")

    def test_a_draft_names_no_version(self):
        self.assertIsNone(version_of_release(release("v0.1.0", draft=True)))

    def test_other_tags_name_no_version(self):
        self.assertIsNone(version_of_release(release("rust-0.1.0")))
        self.assertIsNone(version_of_release(release("v0.1")))
        self.assertIsNone(version_of_release(release("v0.1.0/../x")))


class Precedence(unittest.TestCase):
    def test_versions_order_as_semantic_versioning_says(self):
        ordered = [
            "0.1.0-1",
            "0.1.0-alpha",
            "0.1.0-alpha.1",
            "0.1.0-alpha.beta",
            "0.1.0-beta.2",
            "0.1.0-beta.10",
            "0.1.0-rc.1",
            "0.1.0",
            "0.2.0",
        ]
        self.assertEqual(sorted(reversed(ordered), key=precedence), ordered)


class Editions(unittest.TestCase):
    def test_editions_come_newest_first_from_releases_with_the_reference(self):
        releases = [
            release("v0.1.0-beta.4", "api-reference.tar.gz"),
            release("v0.1.0-beta.10", "x", "api-reference.tar.gz"),
        ]
        found, warnings = editions(releases, "api-reference.tar.gz")
        newest, older = {"version": "0.1.0-beta.10", "asset_id": 1}, {"version": "0.1.0-beta.4", "asset_id": 0}
        self.assertEqual(found, [newest, older])
        self.assertEqual(warnings, [])

    def test_a_release_without_the_reference_has_no_edition_and_is_warned_of(self):
        found, warnings = editions([release("v0.1.0", "conformance-report.json")], "api-reference.tar.gz")
        self.assertEqual(found, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("v0.1.0", warnings[0])

    def test_a_pre_release_gives_an_edition(self):
        releases = [release("v0.1.0-beta.4", "api-reference.tar.gz", prerelease=True)]
        self.assertEqual(editions(releases, "api-reference.tar.gz"), ([{"version": "0.1.0-beta.4", "asset_id": 0}], []))

    def test_drafts_and_other_tags_give_no_edition_and_no_warning(self):
        releases = [
            release("v0.2.0", "api-reference.tar.gz", draft=True),
            release("rust-0.1.0", "api-reference.tar.gz"),
        ]
        self.assertEqual(editions(releases, "api-reference.tar.gz"), ([], []))


class Overlap(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.next = self.root / "packages/itinera/api"

    def test_a_directory_apart_from_the_reference_may_be_emptied(self):
        self.assertIsNone(overlap(self.root / "site", self.next))

    def test_the_working_directory_and_its_parents_are_refused(self):
        here = pathlib.Path.cwd()
        self.assertIn("working directory", overlap(here, self.next))
        self.assertIn("working directory", overlap(here.parent, self.next))

    def test_the_reference_and_what_holds_it_are_refused(self):
        self.assertIn("would remove", overlap(self.next, self.next))
        self.assertIn("would remove", overlap(self.root / "packages", self.next))

    def test_a_directory_inside_the_reference_is_refused(self):
        self.assertIn("into itself", overlap(self.next / "site", self.next))


class BuildSite(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.next = self.root / "api"
        self.next.mkdir()
        (self.next / "index.html").write_text("next")
        self.out = self.root / "site"
        self.archives = {
            "0.1.0-beta.5": archive({"index.html": "beta.5", "modules/step.html": "step 5"}),
            "0.1.0-beta.4": archive({"index.html": "beta.4"}),
        }

    def fetch(self, edition):
        return self.archives[edition["version"]]

    def test_the_newest_release_is_at_the_root_and_every_edition_under_its_name(self):
        found = [{"version": "0.1.0-beta.5", "asset_id": 2}, {"version": "0.1.0-beta.4", "asset_id": 1}]
        build_site(self.out, self.next, found, self.fetch)
        self.assertEqual((self.out / "index.html").read_text(), "beta.5")
        self.assertEqual((self.out / "modules/step.html").read_text(), "step 5")
        self.assertEqual((self.out / "0.1.0-beta.5/index.html").read_text(), "beta.5")
        self.assertEqual((self.out / "0.1.0-beta.4/index.html").read_text(), "beta.4")
        self.assertEqual((self.out / "next/index.html").read_text(), "next")

    def test_before_any_release_the_root_sends_readers_to_next(self):
        build_site(self.out, self.next, [], self.fetch)
        self.assertEqual((self.out / "index.html").read_text(), waiting_page())
        self.assertIn('url=next/', waiting_page())
        self.assertEqual((self.out / "next/index.html").read_text(), "next")

    def test_what_an_earlier_build_left_is_removed(self):
        self.out.mkdir()
        (self.out / "stale.html").write_text("stale")
        build_site(self.out, self.next, [], self.fetch)
        self.assertFalse((self.out / "stale.html").exists())

    def test_an_archive_reaching_outside_its_edition_is_refused(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as tar:
            info = tarfile.TarInfo("../escaped.html")
            tar.addfile(info, io.BytesIO(b""))
        self.archives["0.1.0-beta.4"] = data.getvalue()
        with self.assertRaises(tarfile.TarError):
            build_site(self.out, self.next, [{"version": "0.1.0-beta.4", "asset_id": 1}], self.fetch)
        self.assertFalse((self.out / "escaped.html").exists())


if __name__ == "__main__":
    unittest.main()
