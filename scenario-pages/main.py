"""Write the conformance cases as pages, one set for every tag and one for the default branch."""

import os
import pathlib
import sys
import tempfile

from lib.github_api import GitHub, GitHubError
from lib.scenario_pages import BUILD_FILE, Version, read_features, usable_ref, write_site


def main():
    env = os.environ
    repo = env.get("CONFORMANCE_REPO") or env["REPO"]
    site = pathlib.Path(env.get("SITE_DIR") or "site").resolve()
    github = GitHub(env["GH_TOKEN"])
    try:
        branch = github.get(f"/repos/{repo}")["default_branch"]
        tags = [t["name"] for t in github.get_all(f"/repos/{repo}/tags")]
    except GitHubError as error:
        print(f"::error::{repo} cannot be read: {error}")
        sys.exit(1)

    versions = []
    for name, is_branch in [(branch, True), *((t, False) for t in tags)]:
        problem = usable_ref(name)
        if problem:
            print(f"::warning::{problem}")
            continue
        work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
        try:
            root = github.extract_repository(repo, name, work)
        except GitHubError as error:
            print(f"::error::{repo}@{name} cannot be downloaded: {error}")
            sys.exit(1)
        files = read_features(root)
        print(f"{name}: {len(files)} features.")
        versions.append(Version(name, files, branch=is_branch))

    count = write_site(repo, versions, site, build=env.get("RUN", ""))
    print(f"Wrote {count} files to {site}.")
    with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"build-file={BUILD_FILE}\n")


if __name__ == "__main__":
    main()
