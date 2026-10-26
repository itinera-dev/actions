"""npm packages: what package-lock.json records and the dist-tag a version goes under."""

import json
import pathlib

from lib.release import is_prerelease


def workspace_of(manifest_path):
    """The key package-lock.json gives the package whose package.json is at `manifest_path`, relative to the
    repository's root: its directory, or "" for the root package."""
    directory = pathlib.PurePosixPath(manifest_path).parent.as_posix()
    return "" if directory == "." else directory


def lock_problems(lock, workspace, version):
    """Why the parsed package-lock.json `lock` does not record `version` for the package at `workspace`."""
    packages = lock.get("packages") if isinstance(lock, dict) else None
    entry = packages.get(workspace) if isinstance(packages, dict) else None
    locked = entry.get("version") if isinstance(entry, dict) else None
    if locked != version:
        where = workspace or "the root package"
        return [f"package-lock.json records {locked or 'no version'} for {where}, not {version}; run npm install."]
    return []


def dist_tag_problems(manifest, version):
    """Why the dist-tag the parsed package.json `manifest` sets in `publishConfig.tag` does not suit `version`.

    npm makes any version it publishes `latest` unless told otherwise, so a pre-release goes under `next`, and any
    other version under `latest`, which is npm's own default.
    """
    publish_config = manifest.get("publishConfig", {})
    tag = publish_config.get("tag") if isinstance(publish_config, dict) else None
    if is_prerelease(version) and tag != "next":
        return [f'{version} is a pre-release, so publishConfig.tag must be "next", not {json.dumps(tag)}.']
    if not is_prerelease(version) and tag not in (None, "latest"):
        return [f'{version} is not a pre-release, so publishConfig.tag must be removed, not "{tag}".']
    return []
