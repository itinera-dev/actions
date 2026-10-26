"""Lay out an API reference in editions for GitHub Pages: the newest release, every release and next."""

import os
import sys
import tarfile
from typing import NoReturn

from lib.github_api import GitHub, GitHubError
from lib.reference import build_site, editions, overlap


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def main():
    env = os.environ
    repo, asset, out = env["REPO"], env["ASSET"], env["OUT"]
    github = GitHub(env["GH_TOKEN"])
    if not os.path.isfile(os.path.join(env["NEXT"], "index.html")):
        fail(f"{env['NEXT']} holds no index.html, so it is not a built reference.")
    problem = overlap(out, env["NEXT"])
    if problem:
        fail(problem)
    try:
        found, warnings = editions(github.get_all(f"/repos/{repo}/releases"), asset)
        for warning in warnings:
            print(f"::warning::{warning}")
        build_site(out, env["NEXT"], found, lambda edition: github.download_asset(repo, edition["asset_id"]))
    except (GitHubError, tarfile.TarError, OSError) as error:
        fail(str(error))
    latest = f"latest {found[0]['version']}, " if found else "no release yet, "
    print(f"The reference in {out}: {latest}{len(found)} release(s), and next.")


if __name__ == "__main__":
    main()
