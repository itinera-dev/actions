"""Crates on crates.io: the versions published, and which crates of a workspace a release still has to publish."""

import urllib.parse

from lib.cargo import publishable_members
from lib.registry import get_json

CRATES_IO_API_URL = "https://crates.io/api/v1"


def crate_versions(name, api_url=CRATES_IO_API_URL):
    """Every version of the crate `name` on crates.io, yanked ones included, empty when the crate does not exist."""
    answer = get_json(f"{api_url}/crates/{urllib.parse.quote(name)}")
    return set() if answer is None else {version["num"] for version in answer.get("versions", [])}


def publishable_versions(metadata):
    """The version of each package of a Cargo workspace that may be published, by name, from the output of
    `cargo metadata --no-deps --format-version 1`."""
    return {package["name"]: package["version"] for package in publishable_members(metadata)}


def unpublished(versions, published):
    """The names among `versions`, each crate's version by name, whose version is not in `published[name]`."""
    return sorted(name for name, version in versions.items() if version not in published[name])
