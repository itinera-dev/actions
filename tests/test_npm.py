import unittest

from lib.npm import dist_tag_problems, lock_problems, npm_versions, package_of, workspace_of
from tests.registry_answers import answering, failing


class PackageOf(unittest.TestCase):
    def test_a_manifest_gives_its_name_and_version(self):
        self.assertEqual(package_of({"name": "itinera", "version": "0.1.0"}), ("itinera", "0.1.0"))

    def test_a_manifest_that_is_not_an_object_is_refused(self):
        with self.assertRaisesRegex(ValueError, "must hold an object"):
            package_of(["itinera"])

    def test_a_manifest_without_a_version_is_refused(self):
        with self.assertRaisesRegex(ValueError, '"name" and "version"'):
            package_of({"name": "itinera"})


class WorkspaceOf(unittest.TestCase):
    def test_a_workspace_package_is_keyed_by_its_directory(self):
        self.assertEqual(workspace_of("packages/itinera/package.json"), "packages/itinera")

    def test_the_root_package_is_keyed_by_an_empty_name(self):
        self.assertEqual(workspace_of("package.json"), "")


class LockProblems(unittest.TestCase):
    def test_a_lock_recording_the_version_passes(self):
        lock = {"packages": {"packages/itinera": {"version": "0.1.0"}}}
        self.assertEqual(lock_problems(lock, "packages/itinera", "0.1.0"), [])

    def test_a_lock_recording_another_version_is_refused(self):
        lock = {"packages": {"packages/itinera": {"version": "0.0.0"}}}
        self.assertIn("records 0.0.0 for packages/itinera", lock_problems(lock, "packages/itinera", "0.1.0")[0])

    def test_a_lock_without_the_package_is_refused(self):
        for lock in ({}, [], {"packages": []}, {"packages": {"packages/itinera": "0.1.0"}}):
            with self.subTest(lock=lock):
                self.assertIn("records no version", lock_problems(lock, "packages/itinera", "0.1.0")[0])

    def test_the_root_package_is_named_as_such(self):
        self.assertIn("for the root package", lock_problems({"packages": {}}, "", "0.1.0")[0])


class DistTagProblems(unittest.TestCase):
    def test_a_pre_release_under_next_passes(self):
        self.assertEqual(dist_tag_problems({"publishConfig": {"tag": "next"}}, "0.1.0-beta.1"), [])

    def test_a_pre_release_without_a_dist_tag_is_refused(self):
        for manifest in ({}, {"publishConfig": "next"}):
            with self.subTest(manifest=manifest):
                self.assertIn('must be "next", not null', dist_tag_problems(manifest, "0.1.0-beta.1")[0])

    def test_a_release_without_a_dist_tag_passes(self):
        self.assertEqual(dist_tag_problems({}, "0.1.0"), [])

    def test_a_release_under_latest_passes(self):
        self.assertEqual(dist_tag_problems({"publishConfig": {"tag": "latest"}}, "0.1.0"), [])

    def test_a_release_under_next_is_refused(self):
        self.assertIn("must be removed", dist_tag_problems({"publishConfig": {"tag": "next"}}, "0.1.0")[0])


class NpmVersions(unittest.TestCase):
    def test_a_package_gives_every_version_it_has(self):
        with answering({"versions": {"0.1.0-beta.1": {}, "0.1.0": {}}}):
            self.assertEqual(npm_versions("itinera"), {"0.1.0-beta.1", "0.1.0"})

    def test_a_package_that_does_not_exist_has_no_version(self):
        with failing(404):
            self.assertEqual(npm_versions("itinera"), set())

    def test_a_scoped_package_is_asked_for_with_its_slash_escaped(self):
        with answering({"versions": {}}) as urlopen:
            npm_versions("@itinera-dev/testing")
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://registry.npmjs.org/@itinera-dev%2Ftesting")


if __name__ == "__main__":
    unittest.main()
