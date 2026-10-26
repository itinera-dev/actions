import unittest

from lib.npm import dist_tag_problems, lock_problems, workspace_of


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


if __name__ == "__main__":
    unittest.main()
