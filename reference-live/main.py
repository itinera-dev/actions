"""Check that a reference laid out in editions is live: its root and the newest release name that release."""

import os
import sys
import time
from typing import NoReturn

from lib.github_api import GitHub, GitHubError
from lib.reference import editions
from lib.reference_live import fetch_page, live_pages, root_of, wait_until_live

STALE_DEPLOYMENT = (
    "GitHub Pages keeps serving its previous deployment when a run deploys a commit it has already deployed from a"
    " tag or a release; deploying again from the default branch, with workflow_dispatch, makes the reference live."
)


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def main():
    env = os.environ
    repo, asset = env["REPO"], env["ASSET"]
    try:
        timeout = int(env["TIMEOUT"])
    except ValueError:
        fail(f"The timeout must be a whole number of seconds, not {env['TIMEOUT']!r}.")
    try:
        root = root_of(env["URL"])
    except ValueError as error:
        fail(str(error))
    try:
        found, _ = editions(GitHub(env["GH_TOKEN"]).get_all(f"/repos/{repo}/releases"), asset)
    except GitHubError as error:
        fail(str(error))
    if not found:
        print("::notice::No release has a reference yet, so there is no edition to check.")
        return
    version = found[0]["version"]
    pages = live_pages(root, version)
    nonce = f"{env.get('GITHUB_RUN_ID', '0')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}"
    problems = wait_until_live(pages, version, fetch_page, time.sleep, time.monotonic, timeout, nonce)
    if problems:
        fail(f"The reference is not live after about {timeout} seconds: {' '.join(problems)} {STALE_DEPLOYMENT}")
    print(f"The reference at {pages[0]} is live: it and {pages[1]} name v{version}.")


if __name__ == "__main__":
    main()
