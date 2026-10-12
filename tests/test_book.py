import tomllib
import unittest

from lib.book import (
    dependency_sources,
    locked_packages,
    patch_section,
    patched_manifest,
    pinned_commit,
    publishable_packages,
    unpatched_packages,
)

COMMIT = "c99accf4c8c42bf781b519636925f862a54cc3ca"
GIT = "https://github.com/itinera-dev/itinera-rs"

BOOK = f'''\
[package]
name = "itinera-book"
version = "0.0.0"

[dependencies]
itinera = {{ git = "{GIT}", rev = "{COMMIT}", features = ["async"] }}
futures = {{ version = "0.3", default-features = false }}

[dev-dependencies]
itinera = {{ git = "{GIT}", rev = "{COMMIT}", features = ["testing"] }}
regex = "1"
'''

PACKAGES = {"itinera": "/w/crates/itinera", "itinera-core": "/w/crates/itinera-core"}

METADATA = {
    "workspace_members": ["itinera 0.1.0", "itinera-core 0.1.0", "xtask 0.1.0"],
    "packages": [
        {"id": "itinera 0.1.0", "name": "itinera", "manifest_path": "/w/crates/itinera/Cargo.toml", "publish": None},
        {"id": "itinera-core 0.1.0", "name": "itinera-core", "manifest_path": "/w/crates/itinera-core/Cargo.toml"},
        {"id": "xtask 0.1.0", "name": "xtask", "manifest_path": "/w/crates/xtask/Cargo.toml", "publish": []},
    ],
}


class PinnedCommit(unittest.TestCase):
    def test_a_full_commit_sha_is_pinned(self):
        self.assertEqual(pinned_commit({"commit": COMMIT}), COMMIT)

    def test_anything_but_a_full_commit_sha_is_refused(self):
        for pin in ({"commit": "c99accf"}, {"commit": "main"}, {"tag": COMMIT}, [COMMIT], {"commit": COMMIT.upper()}):
            with self.subTest(pin=pin), self.assertRaisesRegex(ValueError, "full 40-character commit SHA"):
                pinned_commit(pin)


class PublishablePackages(unittest.TestCase):
    def test_every_workspace_member_that_may_be_published_is_found_with_its_directory(self):
        self.assertEqual(publishable_packages(METADATA), PACKAGES)


class DependencySources(unittest.TestCase):
    def test_a_package_from_git_is_patched_at_its_url(self):
        self.assertEqual(dependency_sources(tomllib.loads(BOOK), PACKAGES), {GIT})

    def test_a_package_from_crates_io_is_patched_there(self):
        manifest = {"dependencies": {"itinera": "=0.1.0-beta.1"}, "dev-dependencies": {"itinera": {"version": "1"}}}
        self.assertEqual(dependency_sources(manifest, PACKAGES), {"crates-io"})

    def test_other_dependencies_are_ignored(self):
        self.assertEqual(dependency_sources({"dependencies": {"regex": "1"}}, PACKAGES), set())

    def test_a_renamed_dependency_is_found_by_its_package(self):
        manifest = {"dependencies": {"core": {"package": "itinera-core", "git": GIT}}}
        self.assertEqual(dependency_sources(manifest, PACKAGES), {GIT})

    def test_a_dependency_inherited_from_a_workspace_is_refused(self):
        with self.assertRaisesRegex(ValueError, "inherits itinera from a workspace"):
            dependency_sources({"dependencies": {"itinera": {"workspace": True}}}, PACKAGES)

    def test_a_source_a_patch_cannot_replace_is_refused(self):
        for spec in ({"path": "../itinera"}, {"version": "1", "registry": "other"}):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, "cannot replace"):
                dependency_sources({"dependencies": {"itinera": spec}}, PACKAGES)


class PatchSection(unittest.TestCase):
    def test_a_path_outside_ascii_is_written_as_toml_reads_it(self):
        packages = {"itinera": "/w/caf\u00e9/\U0001f600/itinera"}
        patched = tomllib.loads(patch_section({GIT}, packages))["patch"][GIT]
        self.assertEqual(patched["itinera"]["path"], packages["itinera"])

    def test_every_package_is_replaced_by_its_directory_for_each_source(self):
        patched = tomllib.loads(patch_section({GIT, "crates-io"}, PACKAGES))["patch"]
        expected = {name: {"path": path} for name, path in PACKAGES.items()}
        self.assertEqual(patched, {GIT: expected, "crates-io": expected})


class PatchedManifest(unittest.TestCase):
    def test_the_book_keeps_its_manifest_and_gains_the_patch(self):
        patched = tomllib.loads(patched_manifest(BOOK, PACKAGES))
        self.assertEqual(patched["dependencies"], tomllib.loads(BOOK)["dependencies"])
        self.assertEqual(patched["patch"][GIT]["itinera-core"], {"path": "/w/crates/itinera-core"})

    def test_a_book_that_uses_none_of_the_packages_is_refused(self):
        with self.assertRaisesRegex(ValueError, "depends on none"):
            patched_manifest('[dependencies]\nregex = "1"\n', PACKAGES)

    def test_a_book_that_already_patches_the_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, "already patches"):
            patched_manifest(BOOK + f'\n[patch."{GIT}"]\nitinera = {{ path = "../x" }}\n', PACKAGES)

    def test_a_manifest_that_does_not_parse_is_refused(self):
        with self.assertRaises(ValueError):
            patched_manifest("[package\n", PACKAGES)


LOCK = {
    "package": [
        {"name": "itinera", "version": "0.1.0-beta.1"},
        {"name": "itinera-core", "version": "0.0.0", "source": f"git+{GIT}?rev={COMMIT}#{COMMIT}"},
        {"name": "regex", "version": "1.11.0", "source": "registry+https://github.com/rust-lang/crates.io-index"},
    ]
}


class Lock(unittest.TestCase):
    def test_the_packages_the_lock_holds_are_updated_whatever_their_source(self):
        self.assertEqual(locked_packages(LOCK, PACKAGES), ["itinera", "itinera-core"])

    def test_a_package_the_lock_still_takes_from_a_source_is_not_patched(self):
        self.assertEqual(unpatched_packages(LOCK, PACKAGES), ["itinera-core"])


if __name__ == "__main__":
    unittest.main()
