import unittest

from lib.crates_io import crate_versions, publishable_versions, unpublished
from tests.registry_answers import answering, failing

METADATA = {
    "workspace_members": ["itinera 0.2.0", "itinera-core 0.2.0", "xtask 0.0.0"],
    "packages": [
        {"id": "itinera 0.2.0", "name": "itinera", "version": "0.2.0"},
        {"id": "itinera-core 0.2.0", "name": "itinera-core", "version": "0.2.0", "publish": None},
        {"id": "xtask 0.0.0", "name": "xtask", "version": "0.0.0", "publish": []},
    ],
}


class CrateVersions(unittest.TestCase):
    def test_a_crate_gives_every_version_it_has(self):
        with answering({"versions": [{"num": "0.1.0"}, {"num": "0.2.0"}]}):
            self.assertEqual(crate_versions("itinera"), {"0.1.0", "0.2.0"})

    def test_a_crate_that_does_not_exist_has_no_version(self):
        with failing(404):
            self.assertEqual(crate_versions("itinera"), set())


class PublishableVersions(unittest.TestCase):
    def test_every_workspace_member_that_may_be_published_gives_its_version(self):
        self.assertEqual(publishable_versions(METADATA), {"itinera": "0.2.0", "itinera-core": "0.2.0"})


class Unpublished(unittest.TestCase):
    def test_only_crates_whose_version_is_not_published_are_named(self):
        versions = {"itinera": "0.2.0", "itinera-core": "0.2.0", "itinera-macros": "0.2.0"}
        published = {"itinera": {"0.1.0"}, "itinera-core": {"0.1.0", "0.2.0"}, "itinera-macros": set()}
        self.assertEqual(unpublished(versions, published), ["itinera", "itinera-macros"])


if __name__ == "__main__":
    unittest.main()
