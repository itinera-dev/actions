"""Decide whether a pushed tag becomes a release: its version, its commit, its changelog and the tier claimed."""

import json
import os
import pathlib
import sys
import tempfile
from typing import NoReturn

from lib.conformance import manifest_problems, read_scenarios
from lib.github_api import GitHub, GitHubError
from lib.npm import dist_tag_problems, lock_problems, workspace_of
from lib.release import changelog_section, compare_path, manifest_version, on_branch, tag_problems, tier_problems


def fail(problems) -> NoReturn:
    print("The release gate refused this tag:")
    for problem in problems:
        print(f"::error::{problem}")
    sys.exit(1)


def read(path, found):
    """The text of `path`, or None after adding to `found` why it cannot be read."""
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        found.append(f"{path} cannot be read: {error}")
        return None


def npm_problems(path, text, version):
    """Why the npm package whose package.json at `path` holds `text` cannot release `version`: the lockfile at the
    repository's root must record it, and its dist-tag must suit it."""
    found = []
    lock = read("package-lock.json", found)
    if lock is None:
        return found
    try:
        parsed = json.loads(lock)
    except ValueError as error:
        return [f"package-lock.json cannot be parsed: {error}"]
    return lock_problems(parsed, workspace_of(path), version) + dist_tag_problems(json.loads(text), version)


def main():
    env = os.environ
    repo, tag, branch = env["REPO"], env["TAG"], env["BRANCH"]
    owner = repo.split("/")[0]
    conformance_repo = env.get("CONFORMANCE_REPO") or f"{owner}/conformance"
    github = GitHub(env["GH_TOKEN"])
    try:
        claimed = int(env["TIER"])
    except ValueError:
        fail([f'The input "tier" must be a number, not "{env["TIER"]}".'])

    found = []
    text = read(env["MANIFEST"], found)
    if text is None:
        fail(found)
    try:
        version = manifest_version(env["MANIFEST"], text)
    except ValueError as error:
        fail([str(error)])
    print(f"Tag {tag}, version {version}, tier {claimed} claimed.")
    found += tag_problems(env["REF_TYPE"], tag, version)
    if pathlib.PurePosixPath(env["MANIFEST"]).name == "package.json":
        found += npm_problems(env["MANIFEST"], text, version)

    try:
        status = github.get(compare_path(repo, env["SHA"], branch))["status"]
    except GitHubError as error:
        fail([*found, f"The tagged commit cannot be compared with {branch}: {error}"])
    if not on_branch(status):
        found.append(f"The tagged commit {env['SHA']} is not on {branch}.")

    changelog = read(env["CHANGELOG"], found)
    if changelog is not None and changelog_section(changelog, version) is None:
        found.append(f'{env["CHANGELOG"]} has no notes for {version}, under a heading such as "## [{version}]".')

    text = read("conformance.json", found)
    if text is None:
        fail(found)
    try:
        manifest = json.loads(text)
    except ValueError as error:
        fail([*found, f"conformance.json cannot be read: {error}"])
    shape = manifest_problems(manifest) if isinstance(manifest, dict) else ["conformance.json must hold an object."]
    if shape:
        fail([*found, *shape])

    work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
    try:
        root = github.extract_repository(conformance_repo, manifest["cases"], work)
    except GitHubError as error:
        fail([*found, f"The cases at {conformance_repo}@{manifest['cases']} cannot be downloaded: {error}"])
    found += tier_problems(read_scenarios(root), manifest["proposals"], manifest["capabilities"], claimed)

    if found:
        fail(found)
    print(f"{tag} may be released: cases {conformance_repo}@{manifest['cases']}, tier {claimed}.")


if __name__ == "__main__":
    main()
